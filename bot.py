import requests
import os
import re
import time
import logging
from telegram import Update
from telegram.ext import Updater, MessageHandler, CommandHandler, Filters, CallbackContext

# ================= CONFIG =================
API_KEY      = os.getenv("API_KEY")
BOT_TOKEN    = os.getenv("BOT_TOKEN")
URL          = "https://api.scrapingdog.com/google_maps"
DELAY        = 1.2
MAX_RETRIES  = 3

cancel_flags = {}

# ================= LOGGING =================
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= NUMBER CLEANER =================
def extract_number(raw):
    if not raw:
        return None

    digits = re.sub(r"\D", "", raw)

    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    if len(digits) == 10 and digits[0] in "6789":
        return digits

    return None

# ================= SCRAPER =================
def scrape(keyword):
    for attempt in range(MAX_RETRIES):
        try:
            res = requests.get(
                URL,
                params={
                    "api_key": API_KEY,
                    "query": keyword
                },
                timeout=20
            )

            data = res.json()

            results = data.get("results") or data.get("local_results") or []

            output = []

            for place in results:
                name = place.get("title", "")
                phone = place.get("phone") or place.get("phone_number", "")

                num = extract_number(phone)

                if num and name:
                    output.append((num, name))

            return output

        except Exception as e:
            logger.error(f"[{keyword}] Error: {e}")
            time.sleep(2)

    return []

# ================= COMMANDS =================
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Bot ready ✅\n\nSend keywords like:\nSalon in Delhi\nGym in Mumbai\n\nMulti-line also supported 📂"
    )

def cancel(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    cancel_flags[uid] = True
    update.message.reply_text("Process cancelled ❌")

# ================= MAIN HANDLER =================
def handle(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    cancel_flags[uid] = False

    keywords = update.message.text.split("\n")

    update.message.reply_text(f"Processing {len(keywords)} keyword(s)... ⏳")

    all_data = []
    seen = set()

    for i, kw in enumerate(keywords, start=1):

        if cancel_flags.get(uid):
            update.message.reply_text("Stopped ❌")
            return

        update.message.reply_text(f"[{i}/{len(keywords)}] Searching: {kw}")

        results = scrape(kw)

        for num, name in results:
            if num not in seen:
                seen.add(num)
                all_data.append((num, name))

        time.sleep(DELAY)

    if not all_data:
        update.message.reply_text("No data found ❌")
        return

    # ===== FILE OUTPUT =====
    text_output = "\n".join(f"{num} | {name}" for num, name in all_data)

    update.message.reply_document(
        document=text_output.encode(),
        filename="results.txt"
    )

    update.message.reply_text(f"Done ✅ Total: {len(all_data)} numbers")

# ================= MAIN =================
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("cancel", cancel))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
