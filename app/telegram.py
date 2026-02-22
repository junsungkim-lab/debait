import httpx
from .settings import settings

TELEGRAM_API = "https://api.telegram.org"

async def send_message(chat_id: str, text: str):
    url = f"{TELEGRAM_API}/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json={"chat_id": chat_id, "text": text})
        r.raise_for_status()
        return r.json()
