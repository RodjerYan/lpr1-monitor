import asyncio
import logging
import sys
import time

import httpx
from bs4 import BeautifulSoup

from config import CHANNEL_KEYWORDS, CHANNEL_EXCLUDE_KEYWORDS, POLL_INTERVAL, VK_TOKEN
from vk_client import send_vk, post_to_wall

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

seen_ids: dict[str, set] = {}
warmed_up: set[str] = set()

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

    for msg_wrap in soup.find_all("div", class_="tgme_widget_message_wrap"):
        msg_div = msg_wrap.find("div", class_="tgme_widget_message")
        if not msg_div:
            continue

        msg_id = msg_div.get("data-post", "")
        if not msg_id:
            continue

        if msg_id in seen_ids.setdefault(channel, set()):
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

        seen_ids[channel].add(msg_id)
        msg_url = build_message_url(msg_id)
        results.append((msg_id, matched_kw, text, msg_url))

    return results


async def fetch_channel(channel: str, keywords: list[str]):
    username = channel.lstrip("@")
    url = f"https://t.me/s/{username}"

    html = await fetch_page_text(url)
    if html is None:
        return

    results = parse_messages(html, channel, keywords)

    if not results:
        await asyncio.sleep(0.5)
        html = await fetch_page_text(url)
        if html:
            results = parse_messages(html, channel, keywords)

    if channel not in warmed_up:
        warmed_up.add(channel)
        if results:
            logger.info(f"[{channel}] Прогрев: {len(results)} сообщений, отправка на следующем цикле")
        return

    for msg_id, matched_kw, text, msg_url in results:
        logger.info(f"[{msg_id}] Найдено «{matched_kw}»: {text[:60]}...")

        body = build_body(text, msg_url)

        if VK_TOKEN:
            await asyncio.to_thread(post_to_wall, body)
            await asyncio.to_thread(send_vk, body)


async def _run_all():
    tasks = [asyncio.create_task(fetch_channel(ch, kws)) for ch, kws in CHANNEL_KEYWORDS.items()]
    done, _ = await asyncio.wait(tasks, timeout=10)
    for t in tasks:
        if t not in done and not t.done():
            t.cancel()
    return


async def main():
    for ch in CHANNEL_KEYWORDS:
        seen_ids[ch] = set()

    channels_info = ", ".join(f"{ch}: {kws}" for ch, kws in CHANNEL_KEYWORDS.items())
    logger.info(f"Каналы: {channels_info}, интервал {POLL_INTERVAL}с")

    await _run_all()
    total = sum(len(v) for v in seen_ids.values())
    logger.info(f"Загружено {total} сообщений, слежу за новыми...")

    while True:
        t0 = time.time()
        await _run_all()
        elapsed = time.time() - t0
        remaining = POLL_INTERVAL - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)


if __name__ == "__main__":
    asyncio.run(main())
