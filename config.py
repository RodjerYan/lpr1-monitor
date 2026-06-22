import os
from dotenv import load_dotenv

load_dotenv()

TARGET_CHANNELS = [c.strip() for c in os.getenv("TARGET_CHANNELS", "@lpr1_treugolnik").split(",")]
KEYWORDS = [kw.strip() for kw in os.getenv("FILTER_KEYWORDS", "Белгород").split(",")]
LOCATION_WHITELIST = [loc.strip() for loc in os.getenv("LOCATION_WHITELIST", "").split(",") if loc.strip()]
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))

# Email
YANDEX_EMAIL = os.getenv("YANDEX_EMAIL")
YANDEX_EMAIL_PASSWORD = os.getenv("YANDEX_EMAIL_PASSWORD")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# VK
VK_TOKEN = os.getenv("VK_TOKEN")
VK_USER_ID = os.getenv("VK_USER_ID")

# ntfy.sh push
NTFY_TOPIC = os.getenv("NTFY_TOPIC")

# Screenshot
SCREENSHOT_ENABLED = os.getenv("SCREENSHOT_ENABLED", "").lower() in ("1", "true", "yes")
