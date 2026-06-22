import logging
import smtplib
import time
from email.message import EmailMessage
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import YANDEX_EMAIL, YANDEX_EMAIL_PASSWORD, NOTIFY_EMAIL

logger = logging.getLogger(__name__)

_RETRIES = 3
_DELAY = 3


def _build_msg(subject: str, body: str, screenshot_path: str | None = None):
    if screenshot_path:
        msg = MIMEMultipart()
        msg.attach(MIMEText(body, "plain", "utf-8"))
        try:
            with open(screenshot_path, "rb") as f:
                img = MIMEImage(f.read())
                img.add_header("Content-Disposition", "attachment", filename="screenshot.png")
                msg.attach(img)
        except Exception as e:
            logger.warning(f"Не удалось прикрепить скриншот: {e}")
    else:
        msg = EmailMessage()
        msg.set_content(body)

    msg["From"] = YANDEX_EMAIL
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = subject
    msg["X-Priority"] = "1"
    msg["X-MSMail-Priority"] = "High"
    msg["Importance"] = "High"
    return msg


def _try_send(msg, port: int, use_ssl: bool) -> bool:
    try:
        if use_ssl:
            with smtplib.SMTP_SSL("smtp.yandex.ru", port, timeout=15) as server:
                server.login(YANDEX_EMAIL, YANDEX_EMAIL_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP("smtp.yandex.ru", port, timeout=15) as server:
                server.starttls()
                server.login(YANDEX_EMAIL, YANDEX_EMAIL_PASSWORD)
                server.send_message(msg)
        return True
    except smtplib.SMTPAuthenticationError:
        raise
    except Exception:
        return False


def send_email(subject: str, body: str, screenshot_path: str | None = None) -> bool:
    if not all([YANDEX_EMAIL, YANDEX_EMAIL_PASSWORD, NOTIFY_EMAIL]):
        logger.warning("Email не настроен.")
        return False

    msg = _build_msg(subject, body, screenshot_path)
    ports = [(465, True), (587, False)]

    for attempt in range(_RETRIES):
        for port, ssl in ports:
            try:
                if _try_send(msg, port, ssl):
                    logger.info(f"Письмо отправлено (попытка {attempt+1}, порт {port})")
                    return True
            except smtplib.SMTPAuthenticationError:
                logger.error("Ошибка авторизации SMTP. Нужен пароль приложения.")
                return False

        if attempt < _RETRIES - 1:
            logger.info(f"SMTP не ответил, повтор через {_DELAY}с...")
            time.sleep(_DELAY)

    logger.error(f"Не удалось отправить email после {_RETRIES} попыток.")
    return False
