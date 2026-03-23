import requests
import os
import re
from telegram.ext import Updater, MessageHandler, Filters

API_KEY = os.getenv("API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

def clean_number(phone):
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)

    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) == 10:
        return digits
    return None

def handle_file(update, context):
    try:
        doc = update.message.document

        if not doc.file_name.endswith(".txt"):
            update.message.reply_text("Only .txt file allowed ❌")
            return

        file = doc.get_file()
        file.download("keywords.txt")

        update.message.reply_text("Scraping started... 🔍")

        with open("keywords.txt", "r", encoding="utf-8") as f:
            keywords = [k.strip() for k in f if k.strip()]

        final = []
        seen = set()

        for keyword in keywords:
            url = "https://api.scrapingdog.com/google_maps"

            params = {
                "api_key": API_KEY,
                "query": keyword
            }

            try:
                res = requests.get(url, params=params, timeout=15)
                data = res.json()

                # 🔥 BEST PART (all formats handled)
                results = (
                    data.get("results")
                    or data.get("search_results")
                    or data.get("local_results")
                    or data.get("data")
                    or []
                )

                for place in results:
                    name = place.get("title", "")
                    phone = place.get("phone") or place.get("phone_number")

                    number = clean_number(phone)

                    if name:
                        key = number if number else name

                        if key not in seen:
                            seen.add(key)

                            if number:
                                final.append(f"{number} | {name}")
                            else:
                                final.append(f"❌ | {name}")

            except Exception as e:
                continue

        if not final:
            update.message.reply_text("No data ❌")
            return

        with open("output.txt", "w", encoding="utf-8") as f:
            for item in final:
                f.write(item + "\n")

        update.message.reply_document(open("output.txt", "rb"))

    except Exception as e:
        update.message.reply_text(f"Error: {str(e)}")

# BOT START
updater = Updater(BOT_TOKEN, use_context=True)
dp = updater.dispatcher

dp.add_handler(MessageHandler(Filters.document, handle_file))

print("Bot running...")
updater.start_polling()
updater.idle()
