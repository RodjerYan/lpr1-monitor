import logging

import httpx

from config import NTFY_TOPIC

logger = logging.getLogger(__name__)


def send_ntfy(text: str, title: str = "Lpr1 Monitor") -> bool:
    if not NTFY_TOPIC:
        return False

    clean_title = title.encode("ascii", errors="replace").decode("ascii")

    try:
        resp = httpx.post(
            f"https://ntfy.sh/{NTFY_TOPIC}",
            content=text.encode("utf-8"),
            headers={"Title": clean_title, "Tags": "bell", "Priority": "high"},
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info("Push-уведомление отправлено через ntfy.sh")
            return True
        else:
            logger.warning(f"ntfy.sh error: {resp.status_code} {resp.text[:100]}")
            return False
    except Exception as e:
        logger.error(f"ntfy.sh send error: {e}")
        return False
