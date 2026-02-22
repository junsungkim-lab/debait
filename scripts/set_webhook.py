import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
BASE_URL = os.environ["BASE_URL"].rstrip("/")
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

url = f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook"
webhook_url = f"{BASE_URL}/tg/{WEBHOOK_SECRET}"

print("Setting webhook to:", webhook_url)

r = httpx.post(url, json={"url": webhook_url})
r.raise_for_status()
print(r.json())
