import os
import sys
from telethon.sync import TelegramClient

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]

name = sys.argv[1] if len(sys.argv) > 1 else "session1"
os.makedirs("../data/telegram-sessions", exist_ok=True)
path = f"../data/telegram-sessions/{name}"

with TelegramClient(path, API_ID, API_HASH) as client:
    me = client.get_me()
    print(f"Authorized as: {me.first_name} ({me.phone})")
    print(f"Session saved: {path}.session")
