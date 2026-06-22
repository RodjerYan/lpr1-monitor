import asyncio
import logging
import sys

import httpx
from bs4 import BeautifulSoup

import os as _os

from config import TARGET_CHANNEL, KEYWORDS, POLL_INTERVAL, TELEGRAM_CHAT_ID, SCREENSHOT_ENABLED
from telegram_client import send_telegram, fetch_latest_chat_id
from yandex_client import send_email
from screenshot import take_screenshot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

CHANNEL_USERNAME = TARGET_CHANNEL.lstrip("@")
WEB_URL = f"https://t.me/s/{CHANNEL_USERNAME}"

seen_ids = set()


def extract_text(msg_div: BeautifulSoup) -> str | None:
    for cls in ("tgme_widget_message_text", "tgme_widget_message_caption"):
        el = msg_div.find("div", class_=cls)
        if el:
            text = el.get_text(strip=True)
            if text:
                return text
    return None


def build_message_url(msg_id: str) -> str:
    return f"https://t.me/{msg_id}"


def build_body(text: str, msg_url: str) -> str:
    return f"{text}\n\n🔗 {msg_url}"


async def fetch_new_messages():
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(WEB_URL, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Ошибка загрузки {WEB_URL}: {e}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")
    messages = soup.find_all("div", class_="tgme_widget_message_wrap")

    for msg_wrap in messages:
        msg_div = msg_wrap.find("div", class_="tgme_widget_message")
        if not msg_div:
            continue

        msg_id_attr = msg_div.get("data-post", "")
        if not msg_id_attr:
            continue

        if msg_id_attr in seen_ids:
            continue

        seen_ids.add(msg_id_attr)

        text = extract_text(msg_div)
        if not text:
            continue

        matched_kw = next((kw for kw in KEYWORDS if kw.lower() in text.lower()), None)
        if not matched_kw:
            continue

        logger.info(f"[{msg_id_attr}] Найдено «{matched_kw}»: {text[:60]}...")

        msg_url = build_message_url(msg_id_attr)
        body = build_body(text, msg_url)
        subject = f"🔔 {TARGET_CHANNEL} — {matched_kw}"

        screenshot_path = None
        if SCREENSHOT_ENABLED:
            screenshot_path = await asyncio.to_thread(take_screenshot, msg_url)

        await asyncio.to_thread(send_email, subject=subject, body=body, screenshot_path=screenshot_path)

        if screenshot_path:
            _os.unlink(screenshot_path)

        if TELEGRAM_CHAT_ID:
            await asyncio.to_thread(send_telegram, body)


async def main():
    if not TELEGRAM_CHAT_ID and TELEGRAM_BOT_TOKEN:
        logger.info("TELEGRAM_CHAT_ID не задан. Пытаюсь получить через getUpdates...")
        cid = await asyncio.to_thread(fetch_latest_chat_id)
        if cid:
            logger.info(f"Найден TELEGRAM_CHAT_ID: {cid}. Добавьте его в .env для постоянной работы.")
        else:
            logger.warning("Напишите @Rodjer_bel_bot любое сообщение и перезапустите бота.")

    logger.info(f"Слушаю {WEB_URL}, ищу {KEYWORDS}, интервал {POLL_INTERVAL}с")

    await fetch_new_messages()
    count = len(seen_ids)
    logger.info(f"Загружено {count} существующих сообщений, слежу за новыми...")

    while True:
        await asyncio.sleep(POLL_INTERVAL)
        await fetch_new_messages()


if __name__ == "__main__":
    asyncio.run(main())
