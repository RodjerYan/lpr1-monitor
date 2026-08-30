from __future__ import annotations
import logging
import time

import httpx

from config import VK_TOKEN

logger = logging.getLogger(__name__)

VK_GROUP_ID = -239766241
_members_cache = None
_members_cache_ts = 0
MEMBERS_CACHE_TTL = 300
MAX_RETRIES = 3
RETRY_DELAY = 2


def _vk_request(method: str, params: dict, timeout: int = 15) -> dict | None:
    url = f"https://api.vk.com/method/{method}"
    for attempt in range(MAX_RETRIES):
        try:
            resp = httpx.get(url, params=params, timeout=timeout)
            data = resp.json()
            if "error" in data:
                error = data["error"]
                if error.get("error_code") in (6, 14):
                    delay = RETRY_DELAY * (attempt + 1)
                    logger.warning(f"VK {method}: error_code={error['error_code']}, retry {attempt+1}/{MAX_RETRIES} через {delay}с")
                    time.sleep(delay)
                    continue
                logger.error(f"VK {method} API error: {error}")
                return None
            return data.get("response")
        except Exception as e:
            delay = RETRY_DELAY * (attempt + 1)
            logger.warning(f"VK {method} exception: {e}, retry {attempt+1}/{MAX_RETRIES} через {delay}с")
            time.sleep(delay)
    logger.error(f"VK {method}: все {MAX_RETRIES} попыток исчерпаны")
    return None


def _get_members() -> list[str]:
    global _members_cache, _members_cache_ts

    now = time.time()
    if _members_cache is not None and now - _members_cache_ts < MEMBERS_CACHE_TTL:
        return _members_cache

    members = []
    offset = 0
    while True:
        response = _vk_request("groups.getMembers", {
            "access_token": VK_TOKEN,
            "group_id": 239766241,
            "offset": offset,
            "count": 1000,
            "v": "5.199",
        })
        if response is None:
            break
        items = response.get("items", [])
        members.extend(str(i) for i in items)
        if len(items) < 1000:
            break
        offset += 1000

    cache = members if members else None
    _members_cache = cache
    _members_cache_ts = now
    logger.info(f"VK: получено {len(members)} подписчиков")
    return members


def post_to_wall(text: str) -> bool:
    if not VK_TOKEN:
        return False

    logger.info("VK wall.post: отправка...")
    response = _vk_request("wall.post", {
        "access_token": VK_TOKEN,
        "owner_id": VK_GROUP_ID,
        "from_group": 1,
        "message": text,
        "close_comments": 1,
        "v": "5.199",
    })
    if response:
        logger.info(f"VK: пост на стене OK (post_id={response.get('post_id')})")
        return True
    return False


def send_vk(text: str) -> bool:
    if not VK_TOKEN:
        return False

    members = _get_members()
    if not members:
        return False

    ok = False
    for i in range(0, len(members), 100):
        batch = members[i:i + 100]
        logger.info(f"VK messages.send: batch {i//100+1}, {len(batch)} recipients...")
        response = _vk_request("messages.send", {
            "access_token": VK_TOKEN,
            "peer_ids": ",".join(batch),
            "message": text,
            "random_id": 0,
            "v": "5.199",
        })
        if response:
            logger.info(f"VK: ЛС отправлено {len(batch)} подписчикам OK")
            ok = True

    return ok
