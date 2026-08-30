from __future__ import annotations
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Пара "канал -> список ключевых слов"
raw = os.getenv("CHANNEL_KEYWORDS", "{}")
CHANNEL_KEYWORDS: dict[str, list[str]] = {
    ch: [kw.strip() for kw in kws.split(",")]
    for ch, kws in json.loads(raw).items()
}

# VK
VK_TOKEN = os.getenv("VK_TOKEN")

# Exclude keywords per channel (messages containing these are skipped)
raw_ex = os.getenv("CHANNEL_EXCLUDE_KEYWORDS", "{}")
CHANNEL_EXCLUDE_KEYWORDS: dict[str, list[str]] = {
    ch: [kw.strip().lower() for kw in kws.split(",")]
    for ch, kws in json.loads(raw_ex).items()
}

# Max message length per channel (messages longer than this are skipped)
raw_ml = os.getenv("CHANNEL_MAX_LENGTH", "{}")
CHANNEL_MAX_LENGTH: dict[str, int] = {
    ch: int(v)
    for ch, v in json.loads(raw_ml).items()
}

# Web Push VAPID keys
PUSH_VAPID_PUBLIC = os.getenv("PUSH_VAPID_PUBLIC", "")
PUSH_VAPID_PRIVATE = os.getenv("PUSH_VAPID_PRIVATE", "")
