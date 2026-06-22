import json
import os
from dotenv import load_dotenv

load_dotenv()

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))

# Пара "канал -> список ключевых слов"
raw = os.getenv("CHANNEL_KEYWORDS", "{}")
CHANNEL_KEYWORDS: dict[str, list[str]] = {
    ch: [kw.strip() for kw in kws.split(",")]
    for ch, kws in json.loads(raw).items()
}

# Email
YANDEX_EMAIL = os.getenv("YANDEX_EMAIL")
YANDEX_EMAIL_PASSWORD = os.getenv("YANDEX_EMAIL_PASSWORD")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# VK
VK_TOKEN = os.getenv("VK_TOKEN")
VK_USER_IDS = [uid.strip() for uid in os.getenv("VK_USER_IDS", "").split(",") if uid.strip()]

# ntfy.sh
NTFY_TOPIC = os.getenv("NTFY_TOPIC")

# Screenshot
SCREENSHOT_ENABLED = os.getenv("SCREENSHOT_ENABLED", "").lower() in ("1", "true", "yes")
