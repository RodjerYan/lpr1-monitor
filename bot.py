import asyncio
import json
import logging
import os
import sys
import threading
import time
from http import HTTPStatus
from http.server import HTTPServer, BaseHTTPRequestHandler

import httpx
from bs4 import BeautifulSoup

from config import CHANNEL_KEYWORDS, CHANNEL_EXCLUDE_KEYWORDS, CHANNEL_MAX_LENGTH, POLL_INTERVAL, VK_TOKEN
from vk_client import send_vk, post_to_wall

_log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot.log")
_seen_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seen_ids.json")
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


def _load_seen():
    global seen_ids
    if os.path.exists(_seen_file):
        try:
            with open(_seen_file, "r", encoding="utf-8") as f:
                seen_ids = {ch: data for ch, data in json.load(f).items()}
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


_user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
]


def extract_text(msg_div: BeautifulSoup) -> str | None:
    for cls in ("tgme_widget_message_text", "tgme_widget_message_caption"):
        el = msg_div.find("div", class_=cls)
        if el and (text := el.get_text(strip=True)):
            return text
    return None


def build_message_url(msg_id: str) -> str:
    return f"https://t.me/{msg_id}"


def build_body(text: str, msg_url: str) -> str:
    return f"{text}\n\n🔗 {msg_url}"


async def fetch_page_text(url: str) -> str | None:
    ts = int(time.time() * 1000)
    cache_busted = f"{url}?_={ts}"
    ua = _user_agents[ts % len(_user_agents)]

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                cache_busted,
                headers={
                    "User-Agent": ua,
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                },
            )
            resp.raise_for_status()
            return resp.text
    except asyncio.TimeoutError:
        logger.warning(f"Таймаут {url}")
        return None
    except Exception as e:
        logger.warning(f"Ошибка загрузки {url}: {e}")
        return None


def parse_messages(html: str, channel: str, keywords: list[str]):
    soup = BeautifulSoup(html, "html.parser")
    results = []
    exclude = CHANNEL_EXCLUDE_KEYWORDS.get(channel, [])
    match_all = "*" in keywords
    ch_seen = set(seen_ids.setdefault(channel, []))

    wraps = soup.find_all("div", class_="tgme_widget_message_wrap")
    if not wraps:
        tgme_classes = sorted(set(
            c for d in soup.find_all("div", class_=True)
            for c in d.get("class", []) if "tgme" in c
        ))
        logger.warning(f"[{channel}] NO message wraps! tgme classes: {tgme_classes}, html_len={len(html)}, preview={html[:300]}")

    for msg_wrap in wraps:
        msg_div = msg_wrap.find("div", class_="tgme_widget_message")
        if not msg_div:
            continue

        msg_id = msg_div.get("data-post", "")
        if not msg_id:
            continue

        if msg_id in ch_seen:
            continue

        text = extract_text(msg_div)
        if not text:
            continue

        text_lower = text.lower()
        if any(ex in text_lower for ex in exclude):
            continue

        if match_all:
            matched_kw = "*"
        else:
            matched_kw = next((kw for kw in keywords if kw.lower() in text_lower), None)
            if not matched_kw:
                continue

        ch_seen.add(msg_id)
        msg_url = build_message_url(msg_id)
        results.append((msg_id, matched_kw, text, msg_url))

    seen_ids[channel] = list(ch_seen)
    return results


_startup_diag_done = False


async def fetch_channel(channel: str, keywords: list[str]):
    global _startup_diag_done
    username = channel.lstrip("@")
    url = f"https://t.me/s/{username}"

    html = await fetch_page_text(url)
    if html is None:
        return

    if not _startup_diag_done:
        _startup_diag_done = True
        soup = BeautifulSoup(html, "html.parser")
        wraps = soup.find_all("div", class_="tgme_widget_message_wrap")
        all_div_classes = sorted(set(
            c for d in soup.find_all("div", class_=True)
            for c in d.get("class", [])
        ))
        has_script = "script" in html.lower()
        has_tgme = any("tgme" in c for c in all_div_classes)
        logger.info(f"[STARTUP DIAG] channel={channel} html_len={len(html)} wraps={len(wraps)} has_script={has_script} has_tgme={has_tgme}")
        logger.info(f"[STARTUP DIAG] all_div_classes(first 30)={all_div_classes[:30]}")
        logger.info(f"[STARTUP DIAG] HTML[:1000]={html[:1000]}")
        if wraps:
            msg = wraps[-1].find("div", class_="tgme_widget_message")
            if msg:
                text_el = msg.find("div", class_="tgme_widget_message_text")
                logger.info(f"[STARTUP DIAG] last post_id={msg.get('data-post')} text={text_el.get_text(strip=True)[:100] if text_el else 'NONE'}")

    results = parse_messages(html, channel, keywords)

    if not results:
        await asyncio.sleep(0.5)
        html = await fetch_page_text(url)
        if html:
            results = parse_messages(html, channel, keywords)

    max_len = CHANNEL_MAX_LENGTH.get(channel)

    for msg_id, matched_kw, text, msg_url in results:
        if max_len and len(text) > max_len:
            logger.info(f"[{msg_id}] Пропущен ({len(text)} > {max_len} символов): {text[:80]}...")
            continue

        logger.info(f"[{msg_id}] Найдено «{matched_kw}»: {text[:80]}...")

        body = build_body(text, msg_url)

        if VK_TOKEN:
            logger.info(f"[{msg_id}] Отправка в VK...")
            await asyncio.to_thread(post_to_wall, body)
            await asyncio.to_thread(send_vk, body)
        else:
            logger.warning(f"[{msg_id}] VK_TOKEN не задан, пропуск")


async def _run_all():
    tasks = [asyncio.create_task(fetch_channel(ch, kws)) for ch, kws in CHANNEL_KEYWORDS.items()]
    done, _ = await asyncio.wait(tasks, timeout=10)
    for t in tasks:
        if t not in done and not t.done():
            t.cancel()


last_cycle = 0.0


def _watchdog():
    global last_cycle
    while True:
        time.sleep(60)
        now = time.time()
        since = now - last_cycle
        if since > 600:
            logger.warning(f"Health OK: {since:.0f}s since last cycle, {sum(len(v) for v in seen_ids.values())} msgs tracked")
        if since > 300:
            logger.error(f"No cycles for {since:.0f}s, restarting")
            os._exit(2)


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/diag":
            self._handle_diag()
        else:
            self.send_response(HTTPStatus.OK)
            self.end_headers()
            self.wfile.write(b"OK")

    def do_HEAD(self):
        self.send_response(HTTPStatus.OK)
        self.end_headers()

    def _handle_diag(self):
        import httpx as _httpx
        from bs4 import BeautifulSoup as _BS
        lines = []
        for ch in CHANNEL_KEYWORDS:
            username = ch.lstrip("@")
            url = f"https://t.me/s/{username}"
            try:
                resp = _httpx.get(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0"}, timeout=10)
                html = resp.text
                soup = _BS(html, "html.parser")
                wraps = soup.find_all("div", class_="tgme_widget_message_wrap")
                lines.append(f"{ch}: HTTP {resp.status_code} len={len(html)} wraps={len(wraps)}")
                if wraps:
                    msg = wraps[-1].find("div", class_="tgme_widget_message")
                    if msg:
                        text_el = msg.find("div", class_="tgme_widget_message_text")
                        lines.append(f"  last: post_id={msg.get('data-post')} text={text_el.get_text(strip=True)[:80] if text_el else 'NONE'}")
                else:
                    tgme = sorted(set(c for d in soup.find_all("div", class_=True) for c in d.get("class", []) if "tgme" in c))
                    lines.append(f"  NO WRAPS! tgme={tgme}")
                    lines.append(f"  HTML[:500]={html[:500]}")
            except Exception as e:
                lines.append(f"{ch}: ERROR {e}")
        body = "\n".join(lines).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def _self_ping():
    port = int(os.getenv("PORT", "8080"))
    url = f"http://127.0.0.1:{port}/"
    while True:
        time.sleep(14 * 60)
        try:
            import httpx as _httpx
            resp = _httpx.get(url, timeout=10)
            logger.info(f"Self-ping: {resp.status_code}")
        except Exception as e:
            logger.warning(f"Self-ping error: {e}")


def _start_http():
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    logger.info(f"HTTP server listening on 0.0.0.0:{port}")
    server.serve_forever()


async def main():
    global last_cycle

    _load_seen()

    for ch in CHANNEL_KEYWORDS:
        if ch not in seen_ids:
            seen_ids[ch] = []

    threading.Thread(target=_watchdog, daemon=True).start()
    threading.Thread(target=_start_http, daemon=True).start()
    threading.Thread(target=_self_ping, daemon=True).start()

    channels_info = ", ".join(f"{ch}: {kws}" for ch, kws in CHANNEL_KEYWORDS.items())
    logger.info(f"Каналы: {channels_info}, интервал {POLL_INTERVAL}с")

    await _run_all()
    _save_seen()
    last_cycle = time.time()
    total = sum(len(v) for v in seen_ids.values())
    logger.info(f"Загружено {total} сообщений, слежу за новыми...")

    while True:
        t0 = time.time()
        await _run_all()
        _save_seen()
        last_cycle = time.time()
        elapsed = last_cycle - t0
        remaining = POLL_INTERVAL - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)


if __name__ == "__main__":
    asyncio.run(main())
