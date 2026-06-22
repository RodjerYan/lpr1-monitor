import logging

import httpx

from config import VK_TOKEN

logger = logging.getLogger(__name__)

VK_GROUP_ID = -239766241
_members_cache = None


def _get_members() -> list[str]:
    global _members_cache
    if _members_cache is not None:
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
            items = data.get("response", {}).get("items", [])
            members.extend(str(i) for i in items)
            if len(items) < 1000:
                break
            offset += 1000
        except Exception as e:
            logger.error(f"VK getMembers error: {e}")
            break

    _members_cache = members
    logger.info(f"VK: получено {len(members)} подписчиков")
    return members


GUIDE_POST_ID = None


def pin_guide_post() -> bool:
    global GUIDE_POST_ID
    if not VK_TOKEN or GUIDE_POST_ID:
        return False

    text = (
        "📢 Для получения экстренных оповещений в ЛС:\n"
        "Напишите любое сообщение в это сообщество — после этого бот "
        "сможет присылать вам уведомления напрямую в личные сообщения."
    )

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
        post_id = data.get("response", {}).get("post_id")
        if post_id:
            pin_params = {
                "access_token": VK_TOKEN,
                "owner_id": VK_GROUP_ID,
                "post_id": post_id,
                "v": "5.199",
            }
            pin_resp = httpx.get("https://api.vk.com/method/wall.pin", params=pin_params, timeout=10)
            pin_data = pin_resp.json()
            if pin_data.get("response"):
                GUIDE_POST_ID = post_id
                logger.info("VK: информационный пост закреплён")
                return True
            else:
                logger.warning(f"VK wall.pin error: {pin_data}")
        else:
            logger.warning(f"VK wall.post guide error: {data}")
    except Exception as e:
        logger.error(f"VK pin guide post error: {e}")

    return False


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
            "user_ids": ",".join(batch),
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
