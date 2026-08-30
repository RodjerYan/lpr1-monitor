from __future__ import annotations
import asyncio
import json
import logging
import os
import sys
import threading
import time
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler

from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
import httpx

from config import (
    CHANNEL_KEYWORDS,
    CHANNEL_EXCLUDE_KEYWORDS,
    CHANNEL_MAX_LENGTH,
    VK_TOKEN,
    PUSH_VAPID_PUBLIC,
    PUSH_VAPID_PRIVATE,
)
from vk_client import send_vk, post_to_wall

_dir = os.path.dirname(os.path.abspath(__file__))
_log_file = os.path.join(_dir, "bot.log")
_seen_file = os.path.join(_dir, "seen_ids.json")
_seen_lock = threading.Lock()
_session_name = os.path.join(_dir, "tg_monitor")
_code_file = os.path.join(_dir, "tg_code.txt")
_queue_file = os.path.join(_dir, "vk_queue.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

seen_ids: dict[str, list[str]] = {}
_initial_done = False


def _load_seen():
    global seen_ids
    if os.path.exists(_seen_file):
        try:
            with open(_seen_file, "r", encoding="utf-8") as f:
                seen_ids = {ch: data for ch, data in json.load(f).items()}
            for ch in seen_ids:
                if len(seen_ids[ch]) > 5000:
                    seen_ids[ch] = seen_ids[ch][-5000:]
            total = sum(len(v) for v in seen_ids.values())
            logger.info(f"Загружено {total} known IDs из seen_ids.json")
        except Exception as e:
            logger.warning(f"Ошибка загрузки seen_ids.json: {e}")
            seen_ids = {}


def _save_seen():
    try:
        with open(_seen_file, "w", encoding="utf-8") as f:
            json.dump(seen_ids, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Ошибка сохранения seen_ids.json: {e}")


# --- Push subscriptions ---
_subscriptions_file = os.path.join(_dir, "push_subscriptions.json")
_alerts_file = os.path.join(_dir, "push_alerts.json")


def _load_subscriptions() -> list[dict]:
    if os.path.exists(_subscriptions_file):
        try:
            with open(_subscriptions_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_subs(subs: list[dict]):
    try:
        with open(_subscriptions_file, "w", encoding="utf-8") as f:
            json.dump(subs, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Ошибка сохранения подписок: {e}")


def _load_alerts() -> list[dict]:
    if os.path.exists(_alerts_file):
        try:
            with open(_alerts_file, "r", encoding="utf-8") as f:
                return json.load(f)[-50:]
        except Exception:
            pass
    return []


def _save_alert(alert: dict):
    alerts = _load_alerts()
    alerts.append(alert)
    alerts = alerts[-50:]
    try:
        with open(_alerts_file, "w", encoding="utf-8") as f:
            json.dump(alerts, f, ensure_ascii=False)
    except Exception:
        pass


def _send_push(title: str, body: str):
    subs = _load_subscriptions()
    if not subs:
        return
    from webpush import send_web_push
    for sub in subs:
        try:
            ok = send_web_push(sub, title, body)
            if not ok:
                logger.warning(f"Push failed for {sub.get('endpoint','')[:40]}")
        except Exception as e:
            logger.warning(f"Push error: {e}")


# --- HTTP health check + PWA ---
_MIME = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".svg": "image/svg+xml",
}
_STATIC_DIR = os.path.join(_dir, "static")


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/status":
            self._handle_status()
        elif self.path == "/alerts":
            self._handle_alerts()
        elif self.path == "/" or self.path == "/index.html":
            self._serve_file("index.html", "text/html")
        elif self.path.startswith("/static/"):
            fname = self.path.split("/static/", 1)[1]
            ext = os.path.splitext(fname)[1]
            mime = _MIME.get(ext, "application/octet-stream")
            self._serve_file(fname, mime)
        else:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        if self.path == "/subscribe":
            self._handle_subscribe(body)
        elif self.path == "/unsubscribe":
            self._handle_unsubscribe(body)
        else:
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()

    def do_HEAD(self):
        self.send_response(HTTPStatus.OK)
        self.end_headers()

    def _serve_file(self, fname: str, mime: str):
        fpath = os.path.join(_STATIC_DIR, fname)
        if not os.path.exists(fpath):
            self.send_response(HTTPStatus.NOT_FOUND)
            self.end_headers()
            return
        with open(fpath, "rb") as f:
            data = f.read()
        if fname == "index.html" and PUSH_VAPID_PUBLIC:
            data = data.replace(b"__VAPID_PUBLIC_KEY__", PUSH_VAPID_PUBLIC.encode())
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_status(self):
        queue = _load_queue()
        total_seen = sum(len(v) for v in seen_ids.values())
        subs = _load_subscriptions()
        body = json.dumps({
            "status": "ok",
            "initial_done": _initial_done,
            "channels": list(CHANNEL_KEYWORDS.keys()),
            "seen_ids": total_seen,
            "queue_size": len(queue),
            "push_subscribers": len(subs),
        }, ensure_ascii=False, indent=2)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _handle_alerts(self):
        alerts = _load_alerts()
        body = json.dumps({"alerts": alerts[-20:]}, ensure_ascii=False)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _handle_subscribe(self, raw: bytes):
        try:
            sub = json.loads(raw)
            subs = _load_subscriptions()
            endpoint = sub.get("endpoint", "")
            subs = [s for s in subs if s.get("endpoint") != endpoint]
            subs.append(sub)
            _save_subs(subs)
            logger.info(f"Push подписка: {endpoint[:60]}...")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        except Exception as e:
            self.send_response(HTTPStatus.BAD_REQUEST)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _handle_unsubscribe(self, raw: bytes):
        try:
            sub = json.loads(raw)
            subs = _load_subscriptions()
            endpoint = sub.get("endpoint", "")
            subs = [s for s in subs if s.get("endpoint") != endpoint]
            _save_subs(subs)
            logger.info(f"Push отписка: {endpoint[:60]}...")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
        except Exception:
            self.send_response(HTTPStatus.BAD_REQUEST)
            self.end_headers()

    def log_message(self, *a):
        pass


def _start_http():
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    logger.info(f"HTTP server listening on 0.0.0.0:{port}")
    server.serve_forever()


def _self_ping():
    url = os.getenv("SELF_PING_URL") or os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        port = int(os.getenv("PORT", "8080"))
        url = f"http://127.0.0.1:{port}/"
    logger.info(f"Self-ping URL: {url}")
    while True:
        time.sleep(14 * 60)
        try:
            resp = httpx.get(url, timeout=10)
            logger.info(f"Self-ping: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Self-ping error: {e}")



# --- Message processing ---
def build_body(text: str) -> str:
    return text


def _load_queue() -> list[dict]:
    if os.path.exists(_queue_file):
        try:
            with open(_queue_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_queue(queue: list[dict]):
    try:
        with open(_queue_file, "w", encoding="utf-8") as f:
            json.dump(queue, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Ошибка сохранения очереди: {e}")


def _retry_queue():
    while True:
        time.sleep(60)
        queue = _load_queue()
        if not queue:
            continue
        remaining = []
        for item in queue:
            ok_wall = post_to_wall(item["text"])
            ok_msg = send_vk(item["text"])
            if ok_wall or ok_msg:
                logger.info(f"[queue] Отправлено: {item['text'][:50]}...")
            else:
                remaining.append(item)
                logger.warning(f"[queue] Осталось в очереди: {len(remaining)}")
        _save_queue(remaining)


def _check_length(channel: str, text: str) -> bool:
    max_len = CHANNEL_MAX_LENGTH.get(channel)
    if max_len and len(text) > max_len:
        logger.info(f"[len] Пропущен ({len(text)} > {max_len} символов): {text[:80]}...")
        return False
    return True


def _process_msg(channel: str, text: str, matched_kw: str):
    if not _check_length(channel, text):
        return
    logger.info(f"[{channel}] Найдено «{matched_kw}»: {text[:80]}...")
    body = build_body(text)

    # Save alert
    _save_alert({
        "channel": channel,
        "text": body[:200],
        "keyword": matched_kw,
        "time": time.strftime("%H:%M:%S"),
    })

    # Send push notification
    _send_push(f"🚨 {channel}", body[:200])

    if VK_TOKEN:
        ok_wall = post_to_wall(body)
        ok_msg = send_vk(body)
        if not ok_wall and not ok_msg:
            queue = _load_queue()
            queue.append({"text": body, "channel": channel, "ts": time.time()})
            if len(queue) > 100:
                queue = queue[-100:]
            _save_queue(queue)
            logger.warning(f"[{channel}] Сохранено в очередь ({len(queue)} всего)")
    else:
        logger.warning("VK_TOKEN не задан, пропуск")


# --- Event handler for new messages ---
async def _on_new_msg(event):
    if not _initial_done:
        return

    channel = f"@{event.chat.username}" if event.chat and event.chat.username else str(event.chat_id)
    if channel not in CHANNEL_KEYWORDS:
        return

    keywords = CHANNEL_KEYWORDS[channel]
    exclude = CHANNEL_EXCLUDE_KEYWORDS.get(channel, [])

    post_id = f"{event.chat.username}/{event.id}"
    msg_text = event.text or ""

    with _seen_lock:
        if post_id in seen_ids.get(channel, []):
            return
        seen_ids.setdefault(channel, []).append(post_id)
        if len(seen_ids[channel]) > 10000:
            seen_ids[channel] = seen_ids[channel][-5000:]

    if not msg_text:
        logger.debug(f"[{channel}] {post_id}: пустое сообщение, пропуск")
        return

    text_lower = msg_text.lower()
    if any(ex in text_lower for ex in exclude):
        logger.debug(f"[{channel}] {post_id}: исключено по exclude, пропуск")
        return

    if "*" in keywords:
        matched_kw = "*"
    else:
        matched_kw = next((kw for kw in keywords if kw.lower() in text_lower), None)
        if not matched_kw:
            logger.debug(f"[{channel}] {post_id}: ключевые слова не совпали, пропуск")
            return

    await asyncio.to_thread(_process_msg, channel, msg_text, matched_kw)
    with _seen_lock:
        _save_seen()


# --- Main ---
async def main():
    global _initial_done

    api_id = int(os.environ["TG_API_ID"])
    api_hash = os.environ["TG_API_HASH"]
    phone = os.environ["TG_PHONE"]
    session_str = os.getenv("TG_SESSION")

    _load_seen()

    for ch in CHANNEL_KEYWORDS:
        seen_ids.setdefault(ch, [])

    threading.Thread(target=_start_http, daemon=True).start()
    threading.Thread(target=_self_ping, daemon=True).start()
    threading.Thread(target=_retry_queue, daemon=True).start()

    logger.info(f"Каналы: {', '.join(CHANNEL_KEYWORDS.keys())}")

    if session_str:
        session = StringSession(session_str)
        logger.info("Сессия из TG_SESSION")
    else:
        session = _session_name
        logger.info("Сессия из файла")

    client = TelegramClient(session, api_id, api_hash)

    if session_str:
        logger.info("Подключаюсь к Telegram...")
        try:
            await asyncio.wait_for(client.connect(), timeout=30)
        except asyncio.TimeoutError:
            logger.error("connect() таймаут 30с!")
            return
        logger.info("connect() OK")
        if not await client.is_user_authorized():
            logger.error("TG_SESSION provided but not authorized!")
            return
        logger.info("authorized OK")
        me = await client.get_me()
        logger.info(f"Telegram подключен: {me.first_name} (id={me.id})")
    else:
        def _read_code():
            logger.info(f"Ожидание кода в {_code_file} ...")
            while True:
                if os.path.exists(_code_file):
                    with open(_code_file, "r") as f:
                        code = f.read().strip()
                    if code:
                        os.remove(_code_file)
                        logger.info(f"Код/пароль получен: {code[:2]}***")
                        return code
                time.sleep(2)

        def _read_password():
            logger.info(f"Ожидание облачного пароля в {_code_file} ...")
            while True:
                if os.path.exists(_code_file):
                    with open(_code_file, "r") as f:
                        pw = f.read().strip()
                    if pw:
                        os.remove(_code_file)
                        logger.info(f"Пароль получен: {pw[:2]}***")
                        return pw
                time.sleep(2)

        await client.start(phone=phone, code_callback=_read_code, password=_read_password)
        me = await client.get_me()
        logger.info(f"Telegram подключен: {me.first_name} (id={me.id})")

    for ch, kws in CHANNEL_KEYWORDS.items():
        client.add_event_handler(_on_new_msg, events.NewMessage(chats=ch))

    logger.info("Начинаю инициализацию...")
    try:
        await asyncio.wait_for(client.get_dialogs(), timeout=30)
        logger.info("get_dialogs OK")
    except Exception as e:
        logger.warning(f"get_dialogs timeout/error: {e}")

    async def _init_channel(ch):
        username = ch.lstrip("@")
        logger.info(f"[init] {ch}: get_entity...")
        entity = await client.get_entity(username)
        logger.info(f"[init] {ch}: entity OK, читаю сообщения...")
        count = 0
        async for msg in client.iter_messages(entity, limit=50):
            post_id = f"{username}/{msg.id}"
            with _seen_lock:
                seen_ids.setdefault(ch, [])
                if post_id not in seen_ids[ch]:
                    seen_ids[ch].append(post_id)
                    count += 1
        logger.info(f"[init] {ch}: пометил {count} последних сообщений")

    for ch in CHANNEL_KEYWORDS:
        try:
            await asyncio.wait_for(_init_channel(ch), timeout=30)
        except errors.ChannelPrivateError:
            logger.error(f"[init] {ch}: приватный канал, нет доступа")
        except asyncio.TimeoutError:
            logger.error(f"[init] {ch}: таймаут 30с, пропускаю")
        except Exception as e:
            logger.error(f"[init] {ch}: ошибка {type(e).__name__}: {e}")

    _initial_done = True
    logger.info("Бот запущен (Telethon), слежу за новыми сообщениями...")

    while True:
        await asyncio.sleep(300)
        for ch in CHANNEL_KEYWORDS:
            username = ch.lstrip("@")
            try:
                entity = await client.get_entity(username)
                async for msg in client.iter_messages(entity, limit=10):
                    post_id = f"{username}/{msg.id}"
                    with _seen_lock:
                        if post_id not in seen_ids.get(ch, []):
                            seen_ids.setdefault(ch, []).append(post_id)
                            if msg.text:
                                text_lower = msg.text.lower()
                                exclude = CHANNEL_EXCLUDE_KEYWORDS.get(ch, [])
                                if not any(ex in text_lower for ex in exclude):
                                    keywords = CHANNEL_KEYWORDS[ch]
                                    if "*" in keywords:
                                        matched = "*"
                                    else:
                                        matched = next((kw for kw in keywords if kw.lower() in text_lower), None)
                                    if matched:
                                        logger.info(f"[fallback] {ch}: новое {post_id}")
                                        await asyncio.to_thread(_process_msg, ch, msg.text, matched)
            except Exception as e:
                logger.warning(f"[fallback] {ch}: {e}")

        with _seen_lock:
            _save_seen()


if __name__ == "__main__":
    asyncio.run(main())
