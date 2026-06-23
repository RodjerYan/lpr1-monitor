import sys, asyncio, httpx, time
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding="utf-8")

async def test():
    ts = int(time.time()*1000)
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"https://t.me/s/LiveOnlain?_={ts}", headers={
            "User-Agent": "Mozilla/5.0",
            "Cache-Control": "no-cache"
        })
        print(f"Status: {r.status_code}, Size: {len(r.text)} bytes")
        if "tgme_widget_message_wrap" in r.text:
            print("HAS message divs")
        if "Scheduled" in r.text or "telegram" in r.text.lower():
            print("Page looks like Telegram")

asyncio.run(test())
