import logging
import time

import httpx

from config import VK_TOKEN

logger = logging.getLogger(__name__)

VK_GROUP_ID = -239766241
_members_cache = None
_members_cache_ts = 0
MEMBERS_CACHE_TTL = 300


def _get_members() -> list[str]:
    global _members_cache, _members_cache_ts

    now = time.time()
    if _members_cache is not None and now - _members_cache_ts < MEMBERS_CACHE_TTL:
        return _members_cache

    members = []
    offset = 0
    url = "https://api.vk.com/method/groups.getMembers"
    while True:
        params = {
            "access_token": VK_TOKEN,
            "group_id": 239766241,
            "offset": offset,
            "count": 1000,
            "v": "5.199",
        }
        try:
            resp = httpx.get(url, params=params, timeout=10)
            data = resp.json()
            if "error" in data:
                logger.error(f"VK getMembers API error: {data['error']}")
                break
            items = data.get("response", {}).get("items", [])
            members.extend(str(i) for i in items)
            if len(items) < 1000:
                break
            offset += 1000
        except Exception as e:
            logger.error(f"VK getMembers error: {e}")
            break

    cache = members if members else None
    _members_cache = cache
    _members_cache_ts = now
    logger.info(f"VK: получено {len(members)} подписчиков")
    return members





def post_to_wall(text: str) -> bool:
    if not VK_TOKEN:
        return False

    url = "https://api.vk.com/method/wall.post"
    params = {
        "access_token": VK_TOKEN,
        "owner_id": VK_GROUP_ID,
        "from_group": 1,
        "message": text,
        "close_comments": 1,
        "v": "5.199",
    }

    try:
        logger.info(f"VK wall.post: отправка...")
        resp = httpx.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("response"):
            logger.info(f"VK: пост на стене OK (post_id={data['response'].get('post_id')})")
            return True
        else:
            logger.error(f"VK wall.post ОШИБКА: {data}")
            return False
    except Exception as e:
        logger.error(f"VK wall.post ИСКЛЮЧЕНИЕ: {e}")
        return False


def send_vk(text: str) -> bool:
    if not VK_TOKEN:
        return False

    members = _get_members()
    if not members:
        return False

    url = "https://api.vk.com/method/messages.send"
    ok = False

    for i in range(0, len(members), 100):
        batch = members[i : i + 100]
        params = {
            "access_token": VK_TOKEN,
            "peer_ids": ",".join(batch),
            "message": text,
            "random_id": 0,
            "v": "5.199",
        }
        try:
            logger.info(f"VK messages.send: batch {i//100+1}, {len(batch)} recipients...")
            resp = httpx.get(url, params=params, timeout=15)
            data = resp.json()
            if data.get("response"):
                logger.info(f"VK: ЛС отправлено {len(batch)} подписчикам OK")
                ok = True
            else:
                logger.error(f"VK messages.send ОШИБКА batch {i//100+1}: {data}")
        except Exception as e:
            logger.error(f"VK messages.send ИСКЛЮЧЕНИЕ batch {i//100+1}: {e}")

    return ok
