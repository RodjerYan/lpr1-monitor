import logging

import httpx

from config import VK_TOKEN

logger = logging.getLogger(__name__)

VK_GROUP_ID = -239766241
_members_cache = None


def _get_members() -> list[str]:
    global _members_cache

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
        resp = httpx.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("response"):
            logger.info("VK: пост на стене")
            return True
        else:
            logger.warning(f"VK wall.post error: {data}")
            return False
    except Exception as e:
        logger.error(f"VK wall.post error: {e}")
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
            resp = httpx.get(url, params=params, timeout=15)
            data = resp.json()
            if data.get("response"):
                logger.info(f"VK: лс отправлено {len(batch)} подписчикам")
                ok = True
            else:
                logger.warning(f"VK batch error: {data}")
        except Exception as e:
            logger.error(f"VK batch error: {e}")

    return ok
