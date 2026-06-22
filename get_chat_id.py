import httpx

resp = httpx.get("https://api.telegram.org/bot8646871627:AAEUbfe5hXqlFRc6nXIxKEcltFsyR2YmFqQ/getUpdates", timeout=10)
data = resp.json()
if data.get("ok") and data.get("result"):
    last = data["result"][-1]
    chat_id = last["message"]["chat"]["id"]
    username = last.get("message", {}).get("from", {}).get("username", "-")
    print(f"chat_id: {chat_id}")
    print(f"username: @{username}")
else:
    print("Нет сообщений:", data)
