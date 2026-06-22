# Инструкция

Бот проверяет `t.me/s/lpr1_treugolnik` каждые 30с и шлёт email при слове «Белгород».

## Настройка

**1. Пароль приложения для Yandex.Pочты**
- Зайдите на https://id.yandex.ru/security → **Пароли приложений**
- Создать пароль → тип **Почта** → дайте имя (например `MonitorBot`)
- Скопируйте пароль (формата `xxxxxxx-xxxxxxx`)

**2. Заполните `.env`**
```
YANDEX_EMAIL=ваш-логин@yandex.ru
YANDEX_EMAIL_PASSWORD=скопированный-пароль
NOTIFY_EMAIL=ваш-логин@yandex.ru   (можно тот же)
```

**3. Запуск**
```
pip install -r requirements.txt
python bot.py
```

Письма приходят на почту. Yandex Messenger показывает уведомления о входящих письмах — вы увидите их там.
