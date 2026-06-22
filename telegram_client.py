import logging

import httpx

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def send_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": False,
    }

    try:
        resp = httpx.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("Сообщение отправлено в Telegram")
            return True
        else:
            logger.warning(f"Telegram API error: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return False


def fetch_latest_chat_id() -> str | None:
    if not TELEGRAM_BOT_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        resp = httpx.get(url, timeout=10)
        data = resp.json()
        if not data.get("ok") or not data.get("result"):
            return None
        last = data["result"][-1]
        chat_id = last["message"]["chat"]["id"]
        logger.info(f"Получен chat_id из Telegram: {chat_id}")
        return str(chat_id)
    except Exception as e:
        logger.warning(f"Не удалось получить chat_id: {e}")
        return None
