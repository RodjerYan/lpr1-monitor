import logging
import smtplib
from email.message import EmailMessage
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import YANDEX_EMAIL, YANDEX_EMAIL_PASSWORD, NOTIFY_EMAIL

logger = logging.getLogger(__name__)


def send_email(subject: str, body: str, screenshot_path: str | None = None) -> bool:
    if not all([YANDEX_EMAIL, YANDEX_EMAIL_PASSWORD, NOTIFY_EMAIL]):
        logger.warning("Email не настроен. Заполните YANDEX_EMAIL, YANDEX_EMAIL_PASSWORD, NOTIFY_EMAIL")
        return False

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
