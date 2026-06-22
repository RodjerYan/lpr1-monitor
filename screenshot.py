import logging
import tempfile
from pathlib import Path

from config import SCREENSHOT_ENABLED

logger = logging.getLogger(__name__)

_screenshot_dir: Path | None = None


def _ensure_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        return None


def take_screenshot(message_url: str) -> str | None:
    if not SCREENSHOT_ENABLED:
        return None

    pw = _ensure_playwright()
    if not pw:
        logger.warning("Playwright не установлен. Установите: pip install playwright && python -m playwright install chromium")
        return None

    tmp = tempfile.mktemp(suffix=".png")

    try:
        with pw() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 800, "height": 600})
            page.goto(message_url, wait_until="networkidle", timeout=20000)
            msg = page.query_selector(".tgme_widget_message_wrap")
            if msg:
                msg.screenshot(path=tmp)
            else:
                page.screenshot(path=tmp, full_page=True)
            browser.close()
        size = Path(tmp).stat().st_size
        logger.info(f"Скриншот сохранён: {tmp} ({size} байт)")
        return tmp
    except Exception as e:
        logger.warning(f"Ошибка скриншота {message_url}: {e}")
        return None
