import logging

import httpx

from config import VK_TOKEN, VK_USER_ID

logger = logging.getLogger(__name__)


def send_vk(text: str) -> bool:
    if not VK_TOKEN or not VK_USER_ID:
        return False

    url = "https://api.vk.com/method/messages.send"
    params = {
        "access_token": VK_TOKEN,
        "user_id": VK_USER_ID,
        "message": text,
        "random_id": 0,
        "v": "5.199",
    }

    try:
        resp = httpx.get(url, params=params, timeout=10)
        data = resp.json()
        if data.get("response"):
            logger.info("Сообщение отправлено в VK")
            return True
        else:
            logger.warning(f"VK API error: {data}")
            return False
    except Exception as e:
        logger.error(f"VK send error: {e}")
        return False
