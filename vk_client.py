import logging

import httpx

from config import VK_TOKEN, VK_USER_IDS

logger = logging.getLogger(__name__)

VK_GROUP_ID = -239766241


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
            logger.info("VK: пост опубликован на стене сообщества")
            return True
        else:
            logger.warning(f"VK wall.post error: {data}")
            return False
    except Exception as e:
        logger.error(f"VK wall.post error: {e}")
        return False


def send_vk(text: str) -> bool:
    if not VK_TOKEN or not VK_USER_IDS:
        return False

    url = "https://api.vk.com/method/messages.send"
    ok = False

    for uid in VK_USER_IDS:
        params = {
            "access_token": VK_TOKEN,
            "user_id": uid,
            "message": text,
            "random_id": 0,
            "v": "5.199",
        }
        try:
            resp = httpx.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get("response"):
                logger.info(f"VK: лс отправлено {uid}")
                ok = True
            else:
                logger.warning(f"VK error для {uid}: {data}")
        except Exception as e:
            logger.error(f"VK send error для {uid}: {e}")

    return ok
