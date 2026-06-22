# Lpr1 Monitor Bot

Бот мониторит канал @lpr1_treugolnik и шлёт email при слове «Белгород».

## Развернуто на Railway

Бот запущен и работает 24/7 на Railway.app.
Проект: https://railway.com/project/62530149-0874-4d6b-b1a0-2a9272473d5e

## Переменные окружения (уже заданы в Railway)

- `YANDEX_EMAIL` = sani415@yandex.ru
- `YANDEX_EMAIL_PASSWORD` = пароль приложения
- `NOTIFY_EMAIL` = sani415@yandex.ru
- `TARGET_CHANNEL` = @lpr1_treugolnik
- `FILTER_KEYWORD` = Белгород
- `POLL_INTERVAL` = 30

## Для локального запуска

```
pip install -r requirements.txt
cp .env.example .env
# заполнить .env
python bot.py
```
