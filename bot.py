import asyncio
import logging
import os as _os
import sys

import httpx
from bs4 import BeautifulSoup

from config import CHANNEL_KEYWORDS, POLL_INTERVAL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, VK_TOKEN, NTFY_TOPIC, SCREENSHOT_ENABLED
from telegram_client import send_telegram, fetch_latest_chat_id
from vk_client import send_vk, post_to_wall, pin_guide_post
from yandex_client import send_email
from ntfy_client import send_ntfy
from screenshot import take_screenshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

seen_ids: dict[str, set] = {}


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


async def fetch_channel(channel: str, keywords: list[str]):
    username = channel.lstrip("@")
    url = f"https://t.me/s/{username}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            resp.raise_for_status()
    except Exception as e:
        logger.warning(f"Ошибка загрузки {url}: {e}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")

    for msg_wrap in soup.find_all("div", class_="tgme_widget_message_wrap"):
        msg_div = msg_wrap.find("div", class_="tgme_widget_message")
        if not msg_div:
            continue

        msg_id = msg_div.get("data-post", "")
        if not msg_id:
            continue

        if msg_id in seen_ids.setdefault(channel, set()):
            continue

        seen_ids[channel].add(msg_id)

        text = extract_text(msg_div)
        if not text:
            continue

        matched_kw = next((kw for kw in keywords if kw.lower() in text.lower()), None)
        if not matched_kw:
            continue

        logger.info(f"[{msg_id}] Найдено «{matched_kw}»: {text[:60]}...")

        msg_url = build_message_url(msg_id)
        body = build_body(text, msg_url)
        subject = f"🔔 {channel} — {matched_kw}"

        screenshot_path = None
        if SCREENSHOT_ENABLED:
            screenshot_path = await asyncio.to_thread(take_screenshot, msg_url)

        await asyncio.to_thread(send_email, subject=subject, body=body, screenshot_path=screenshot_path)

        if screenshot_path:
            _os.unlink(screenshot_path)

        if TELEGRAM_CHAT_ID:
            await asyncio.to_thread(send_telegram, body)
        if VK_TOKEN:
            await asyncio.to_thread(post_to_wall, body)
            await asyncio.to_thread(send_vk, body)
        if NTFY_TOPIC:
            await asyncio.to_thread(send_ntfy, body, title=subject)


async def main():
    for ch in CHANNEL_KEYWORDS:
        seen_ids[ch] = set()

    if not TELEGRAM_CHAT_ID and TELEGRAM_BOT_TOKEN:
        cid = await asyncio.to_thread(fetch_latest_chat_id)
        if cid:
            logger.info(f"TELEGRAM_CHAT_ID: {cid}")
        else:
            logger.warning("Напишите @Rodjer_bel_bot любое сообщение.")

    if VK_TOKEN:
        await asyncio.to_thread(pin_guide_post)

    channels_info = ", ".join(f"{ch}: {kws}" for ch, kws in CHANNEL_KEYWORDS.items())
    logger.info(f"Каналы: {channels_info}, интервал {POLL_INTERVAL}с")

    for ch, kws in CHANNEL_KEYWORDS.items():
        await fetch_channel(ch, kws)
    total = sum(len(v) for v in seen_ids.values())
    logger.info(f"Загружено {total} сообщений, слежу за новыми...")

    while True:
        await asyncio.sleep(POLL_INTERVAL)
        for ch, kws in CHANNEL_KEYWORDS.items():
            await fetch_channel(ch, kws)


if __name__ == "__main__":
    asyncio.run(main())
