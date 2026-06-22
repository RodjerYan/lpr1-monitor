import os
from dotenv import load_dotenv

load_dotenv()

TARGET_CHANNEL = os.getenv("TARGET_CHANNEL", "@lpr1_treugolnik")
KEYWORD = os.getenv("FILTER_KEYWORD", "Белгород")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))

# Email для отправки (SMTP Yandex)
YANDEX_EMAIL = os.getenv("YANDEX_EMAIL")
YANDEX_EMAIL_PASSWORD = os.getenv("YANDEX_EMAIL_PASSWORD")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL")
