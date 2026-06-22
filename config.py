import os
from dotenv import load_dotenv

load_dotenv()

TARGET_CHANNEL = os.getenv("TARGET_CHANNEL", "@lpr1_treugolnik")
KEYWORDS = [kw.strip() for kw in os.getenv("FILTER_KEYWORDS", "Белгород").split(",")]
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))

# Email для отправки (SMTP Yandex)
YANDEX_EMAIL = os.getenv("YANDEX_EMAIL")
YANDEX_EMAIL_PASSWORD = os.getenv("YANDEX_EMAIL_PASSWORD")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL")
