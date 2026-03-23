import requests
import os
import time
from telegram import Update
from telegram.ext import Updater, MessageHandler, CommandHandler, Filters, CallbackContext

API_KEY = os.getenv("API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ─────────────────────────────────────────
# /start command handler
# ─────────────────────────────────────────
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "👋 *Welcome to Google Maps Scraper Bot!*\n\n"
        "📌 *How to use:*\n"
        "1️⃣ Send a `.txt` file with one keyword per line\n"
        "2️⃣ OR just type keyword(s) directly as plain text (one per line)\n\n"
        "📤 *Output:*\n"
        "• `output_full.txt` → `mobile : name`\n"
        "• `output_numbers.txt` → only mobile numbers\n\n"
        "⚙️ Features: retry system, delay, progress updates at 25/50/75/100%",
        parse_mode="Markdown"
    )


# ─────────────────────────────────────────
# Core scraping logic with retry + delay
# ─────────────────────────────────────────
def scrape_keyword(keyword: str, retries: int = 3, delay: int = 5) -> list:
    url = "https://api.scrapingdog.com/google_maps"
    params = {"api_key": API_KEY, "query": keyword}

    for attempt in range(1, retries + 1):
        try:
            res = requests.get(url, params=params, timeout=15)
            data = res.json()
            results = data.get("search_results") or data.get("data") or []
            found = []
            for place in results:
                phone = place.get("phone")
                name = place.get("title")
                if phone and name:
                    found.append((phone.strip(), name.strip()))
            return found
        except Exception as e:
            if attempt < retries:
                time.sleep(delay * attempt)   # progressive delay: 5s, 10s, 15s
            else:
                return []   # give up after all retries
    return []


# ─────────────────────────────────────────
# Progress tracker
# ─────────────────────────────────────────
def get_progress_message(done: int, total: int) -> str | None:
    pct = (done / total) * 100
    if pct >= 100:
        return "✅ *100% Done!* Processing results..."
    elif pct >= 75 and (done - 1) / total * 100 < 75:
        return "🔵 *75% complete...* Keep going!"
    elif pct >= 50 and (done - 1) / total * 100 < 50:
        return "🟡 *50% complete...* Halfway there!"
    elif pct >= 25 and (done - 1) / total * 100 < 25:
        return "🟠 *25% complete...* Good start!"
    return None


# ─────────────────────────────────────────
# Main processing function
# ─────────────────────────────────────────
def process_keywords(keywords: list, update: Update):
    total = len(keywords)
    if total == 0:
        update.message.reply_text("❌ No keywords found.")
        return

    update.message.reply_text(
        f"🚀 Scraping started for *{total}* keyword(s)...\n"
        "Progress updates at 25%, 50%, 75%, 100% 📊",
        parse_mode="Markdown"
    )

    results_list = []

    for i, keyword in enumerate(keywords, start=1):
        found = scrape_keyword(keyword)
        results_list.extend(found)

        # send progress notifications
        msg = get_progress_message(i, total)
        if msg:
            update.message.reply_text(msg, parse_mode="Markdown")

        # small delay between keywords to avoid rate limiting
        if i < total:
            time.sleep(2)

    # deduplicate by phone number
    seen_phones = set()
    unique_results = []
    for phone, name in results_list:
        if phone not in seen_phones:
            seen_phones.add(phone)
            unique_results.append((phone, name))

    if not unique_results:
        update.message.reply_text("❌ Koi data nahi mila. Try different keywords.")
        return

    # ── File 1: mobile : name ──
    full_path = "output_full.txt"
    with open(full_path, "w", encoding="utf-8") as f:
        for phone, name in unique_results:
            f.write(f"{phone} : {name}\n")

    # ── File 2: only mobile numbers ──
    numbers_path = "output_numbers.txt"
    with open(numbers_path, "w", encoding="utf-8") as f:
        for phone, _ in unique_results:
            f.write(f"{phone}\n")

    count = len(unique_results)
    update.message.reply_text(
        f"✅ *Scraping complete!*\n📋 Total unique results: *{count}*\n\n"
        "📁 Sending both output files...",
        parse_mode="Markdown"
    )

    # send both files
    with open(full_path, "rb") as f:
        update.message.reply_document(
            document=f,
            filename="output_full.txt",
            caption="📄 Full output: `mobile : name`",
            parse_mode="Markdown"
        )

    with open(numbers_path, "rb") as f:
        update.message.reply_document(
            document=f,
            filename="output_numbers.txt",
            caption="📱 Numbers only output",
            parse_mode="Markdown"
        )


# ─────────────────────────────────────────
# Handler: .txt file upload
# ─────────────────────────────────────────
def handle_file(update: Update, context: CallbackContext):
    try:
        document = update.message.document

        if not document.file_name.endswith(".txt"):
            update.message.reply_text("⚠️ Only `.txt` files are allowed.", parse_mode="Markdown")
            return

        file = context.bot.get_file(document.file_id)
        file.download("keywords.txt")

        with open("keywords.txt", "r", encoding="utf-8") as f:
            keywords = [line.strip() for line in f if line.strip()]

        process_keywords(keywords, update)

    except Exception as e:
        update.message.reply_text(f"❌ Error: {str(e)}")


# ─────────────────────────────────────────
# Handler: plain text message
# ─────────────────────────────────────────
def handle_text(update: Update, context: CallbackContext):
    try:
        text = update.message.text.strip()

        # ignore /start and other commands caught here
        if text.startswith("/"):
            return

        keywords = [line.strip() for line in text.splitlines() if line.strip()]

        if not keywords:
            update.message.reply_text("⚠️ Please send at least one keyword.")
            return

        process_keywords(keywords, update)

    except Exception as e:
        update.message.reply_text(f"❌ Error: {str(e)}")


# ─────────────────────────────────────────
# Bot startup
# ─────────────────────────────────────────
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.document, handle_file))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    print("✅ Bot is running...")
    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
  
