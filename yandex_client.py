import logging
import smtplib
from email.message import EmailMessage

from config import YANDEX_EMAIL, YANDEX_EMAIL_PASSWORD, NOTIFY_EMAIL

logger = logging.getLogger(__name__)


def send_email(subject: str, body: str) -> bool:
    if not all([YANDEX_EMAIL, YANDEX_EMAIL_PASSWORD, NOTIFY_EMAIL]):
        logger.warning("Email не настроен. Заполните YANDEX_EMAIL, YANDEX_EMAIL_PASSWORD, NOTIFY_EMAIL")
        return False

    msg = EmailMessage()
    msg["From"] = YANDEX_EMAIL
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL("smtp.yandex.ru", 465, timeout=15) as server:
            server.login(YANDEX_EMAIL, YANDEX_EMAIL_PASSWORD)
            server.send_message(msg)
        logger.info(f"Письмо отправлено на {NOTIFY_EMAIL}")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("Ошибка авторизации SMTP. Нужен пароль приложения, а не обычный пароль.")
        return False
    except Exception as e:
        logger.error(f"Ошибка отправки email: {e}")
        return False
