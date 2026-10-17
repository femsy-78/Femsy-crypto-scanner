import json
import os
import urllib.request

token = os.environ["TELEGRAM_BOT_TOKEN"]
url = f"https://api.telegram.org/bot{token}/getUpdates"

with urllib.request.urlopen(url, timeout=20) as response:
    data = json.load(response)

if not data.get("ok"):
    raise SystemExit("Telegram API request failed.")

updates = data.get("result", [])

if not updates:
    raise SystemExit(
        "No messages found. Send /start to your bot and try again."
    )

found = False

for update in updates:
    message = update.get("message", {})
    chat = message.get("chat", {})

    if chat.get("type") == "private" and chat.get("id"):
        print("Your Telegram chat ID is:", chat["id"])
        found = True
        break

if not found:
    raise SystemExit("No private chat found. Send a message to your bot.")
