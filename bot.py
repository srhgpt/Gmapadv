import requests
import os
import re
import time
import logging
from telegram import Update
from telegram.ext import Updater, MessageHandler, CommandHandler, Filters, CallbackContext

# Logging
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

API_KEY      = os.getenv("API_KEY")
BOT_TOKEN    = os.getenv("BOT_TOKEN")
SCRAPING_URL = "https://api.scrapingdog.com/google_maps"
DELAY        = 1.5
MAX_RETRIES  = 2

cancel_flags = {}

# Number extractor
def extract_indian_number(raw):
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

# Scraper
def scrape_keyword(keyword):
    attempt = 0
    while attempt <= MAX_RETRIES:
        try:
            res = requests.get(
                SCRAPING_URL,
                params={"api_key": API_KEY, "query": keyword},
                timeout=20
            )
            data = res.json()

            results = data.get("local_results") or []

            entries = []
            for place in results:
                raw_phone = place.get("phone", "")
                name = place.get("title", "")

                number = extract_indian_number(raw_phone)
                if number and name:
                    entries.append((number, name))

            return entries

        except Exception as e:
            logger.error(e)

        attempt += 1
        time.sleep(2)

    return []

# Commands
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Bot working ✅")

def cancel(update: Update, context: CallbackContext):
    uid = update.effective_user.id
    cancel_flags[uid] = True
    update.message.reply_text("Cancelled ❌")

# Main handler
def handle_text(update: Update, context: CallbackContext):
    keywords = update.message.text.split("\n")

    all_entries = []
    seen = set()

    for keyword in keywords:
        entries = scrape_keyword(keyword)

        for number, name in entries:
            if number not in seen:
                seen.add(number)
                all_entries.append((number, name))

        time.sleep(DELAY)

    if not all_entries:
        update.message.reply_text("No data ❌")
        return

    numbers_txt = "\n".join(num for num, _ in all_entries)

    update.message.reply_document(
        document=numbers_txt.encode(),
        filename="numbers.txt"
    )

# MAIN
def main():
    updater = Updater(BOT_TOKEN, use_context=True)

    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("cancel", cancel))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
