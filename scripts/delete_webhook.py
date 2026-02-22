import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook"

r = httpx.post(url, json={})
r.raise_for_status()
print(r.json())
