import asyncio
import logging
import sys

import httpx
from bs4 import BeautifulSoup

from config import TARGET_CHANNEL, KEYWORD, POLL_INTERVAL
from yandex_client import send_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

CHANNEL_USERNAME = TARGET_CHANNEL.lstrip("@")
WEB_URL = f"https://t.me/s/{CHANNEL_USERNAME}"

seen_ids = set()


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

        text_div = msg_div.find("div", class_="tgme_widget_message_text")
        if not text_div:
            continue

        text = text_div.get_text(strip=True)
        if not text:
            continue

        seen_ids.add(msg_id_attr)

        if KEYWORD.lower() not in text.lower():
            continue

        logger.info(f"[{msg_id_attr}] Найдено: {text[:60]}...")
        await asyncio.to_thread(
            send_email,
            subject=f"🔔 {TARGET_CHANNEL} — {KEYWORD}",
            body=text,
        )


async def main():
    logger.info(f"Слушаю {WEB_URL}, ищу «{KEYWORD}», интервал {POLL_INTERVAL}с")

    # При старте загружаем уже существующие сообщения, чтобы не спамить
    await fetch_new_messages()
    count = len(seen_ids)
    logger.info(f"Загружено {count} существующих сообщений, слежу за новыми...")

    while True:
        await asyncio.sleep(POLL_INTERVAL)
        await fetch_new_messages()


if __name__ == "__main__":
    asyncio.run(main())
