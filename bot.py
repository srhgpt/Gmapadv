import requests
import os
import re
import time
import logging
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ─── Config ──────────────────────────────────────────────────────────────────
API_KEY      = os.getenv("API_KEY")
BOT_TOKEN    = os.getenv("BOT_TOKEN")
SCRAPING_URL = "https://api.scrapingdog.com/google_maps"
DELAY        = 1.5   # seconds between API calls
MAX_RETRIES  = 2     # retry failed keywords

# Per-user cancel flag  {user_id: bool}
cancel_flags: dict[int, bool] = {}


# ─── Indian Number Extractor ─────────────────────────────────────────────────

def extract_indian_number(raw: str) -> str | None:
    """
    Kisi bhi format ka number le aur clean 10-digit Indian mobile return kare.
    Returns None if not a valid Indian mobile.
    """
    if not raw:
        return None

    # sirf digits nikalo
    digits = re.sub(r"\D", "", raw)

    # +91 / 91 prefix hata do
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    # valid Indian mobile: 10 digits, starts with 6/7/8/9
    if len(digits) == 10 and digits[0] in "6789":
        return digits

    return None


# ─── Scraper ─────────────────────────────────────────────────────────────────

def scrape_keyword(keyword: str) -> list[tuple[str, str]]:
    """
    Ek keyword scrape karo.
    Returns list of (clean_number, name) tuples.
    """
    attempt = 0
    while attempt <= MAX_RETRIES:
        try:
            res = requests.get(
                SCRAPING_URL,
                params={"api_key": API_KEY, "query": keyword},
                timeout=20
            )
            res.raise_for_status()
            data = res.json()

            # sabhi possible keys try karo maximum data ke liye
            results = (
                data.get("search_results")
                or data.get("local_results")
                or data.get("places")
                or data.get("data")
                or data.get("results")
                or []
            )

            entries = []
            for place in results:
                raw_phone = (
                    place.get("phone")
                    or place.get("phone_number")
                    or place.get("mobile")
                    or ""
                ).strip()

                name = (
                    place.get("title")
                    or place.get("name")
                    or place.get("business_name")
                    or ""
                ).strip()

                number = extract_indian_number(raw_phone)
                if number and name:
                    entries.append((number, name))

            logger.info(f"'{keyword}' → {len(entries)} results")
            return entries

        except requests.exceptions.Timeout:
            logger.warning(f"Timeout attempt {attempt+1} for: {keyword}")
        except requests.exceptions.HTTPError as e:
            logger.warning(f"HTTP {e.response.status_code} for: {keyword}")
            break  # HTTP error pe retry nahi
        except Exception as e:
            logger.error(f"Error for '{keyword}': {e}")

        attempt += 1
        time.sleep(2)  # retry se pehle wait

    return []


# ─── Commands ────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Google Maps Scraper Bot*\n\n"
        "📌 *Kaise use karein:*\n"
        "• Ek ya multiple `.txt` files bhejo\n"
        "• Har line mein ek keyword hona chahiye\n"
        "  Example: `dental clinic Mumbai`\n\n"
        "• Ya seedha keywords type karo (ek per line)\n\n"
        "📤 *Output milega:*\n"
        "• `numbers.txt` — sirf Indian mobile numbers\n"
        "• `results.txt` — number : business name\n\n"
        "⚙️ *Commands:*\n"
        "/status — bot ki state dekho\n"
        "/cancel — scraping rok do\n",
        parse_mode="Markdown"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    running = cancel_flags.get(uid) is False  # False means actively running
    state = "🟢 Scraping chal rahi hai..." if running else "😴 Koi scraping nahi chal rahi"
    await update.message.reply_text(f"*Bot Status:* Online ✅\n{state}", parse_mode="Markdown")


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if cancel_flags.get(uid) is False:
        cancel_flags[uid] = True
        await update.message.reply_text("🛑 Scraping cancel ho rahi hai... ruko thoda.")
    else:
        await update.message.reply_text("⚠️ Koi active scraping nahi hai abhi.")


# ─── Core Processor ──────────────────────────────────────────────────────────

async def process_keywords(
    update: Update,
    keywords: list[str]
):
    uid = update.effective_user.id
    total = len(keywords)

    await update.message.reply_text(
        f"📋 *{total} keywords* mile\n🚀 Scraping shuru ho rahi hai...",
        parse_mode="Markdown"
    )

    cancel_flags[uid] = False  # mark as running

    all_entries: list[tuple[str, str]] = []
    seen_numbers: set[str] = set()

    # milestones pe hi message bhejo: 25, 50, 75, 100
    milestones = {25, 50, 75, 100}
    last_milestone = 0

    for idx, keyword in enumerate(keywords, start=1):

        # cancel check
        if cancel_flags.get(uid):
            await update.message.reply_text("🛑 Scraping cancel kar di gayi.")
            cancel_flags.pop(uid, None)
            return

        entries = scrape_keyword(keyword)

        for number, name in entries:
            if number not in seen_numbers:
                seen_numbers.add(number)
                all_entries.append((number, name))

        # progress — sirf 25/50/75/100 pe
        pct = int((idx / total) * 100)
        for m in sorted(milestones):
            if pct >= m > last_milestone:
                await update.message.reply_text(f"{'✅' if m == 100 else '⏳'} {m}% processed")
                last_milestone = m

        time.sleep(DELAY)  # API ko aaram do

    cancel_flags.pop(uid, None)

    if not all_entries:
        await update.message.reply_text("❌ Koi Indian number nahi mila. Keywords check karo.")
        return

    # ── Build output files ──
    numbers_txt = "\n".join(num for num, _ in all_entries)
    results_txt = "\n".join(f"{num} : {name}" for num, name in all_entries)

    numbers_bytes = numbers_txt.encode("utf-8")
    results_bytes = results_txt.encode("utf-8")

    await update.message.reply_text(
        f"✅ *Done!*\n"
        f"📞 Total numbers: *{len(all_entries)}*\n"
        f"📁 Dono files neeche hain 👇",
        parse_mode="Markdown"
    )

    await update.message.reply_document(
        document=numbers_bytes,
        filename="numbers.txt",
        caption="📱 Sirf Indian numbers"
    )
    await update.message.reply_document(
        document=results_bytes,
        filename="results.txt",
        caption="📋 Number : Business Name"
    )


# ─── File Handler ─────────────────────────────────────────────────────────────

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if cancel_flags.get(uid) is False:
        await update.message.reply_text("⚠️ Pehle se scraping chal rahi hai. /cancel karo pehle.")
        return

    document = update.message.document

    if not document.file_name.lower().endswith(".txt"):
        await update.message.reply_text("❌ Sirf `.txt` file bhejo.")
        return

    # file download karo memory mein
    tg_file = await document.get_file()
    raw_bytes = await tg_file.download_as_bytearray()
    content = raw_bytes.decode("utf-8", errors="ignore")

    keywords = [line.strip() for line in content.splitlines() if line.strip()]

    if not keywords:
        await update.message.reply_text("❌ File khali hai ya koi valid keyword nahi mila.")
        return

    await process_keywords(update, keywords)


# ─── Text Handler (direct keywords) ──────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if cancel_flags.get(uid) is False:
        await update.message.reply_text("⚠️ Pehle se scraping chal rahi hai. /cancel karo pehle.")
        return

    text = update.message.text.strip()
    if not text:
        return

    keywords = [line.strip() for line in text.splitlines() if line.strip()]

    if not keywords:
        return

    await process_keywords(update, keywords)


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    if not API_KEY or not BOT_TOKEN:
        logger.error("❌ API_KEY ya BOT_TOKEN set nahi hai!")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # multiple files support — sab document messages handle honge
    app.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("🤖 Bot chal raha hai...")
    app.run_polling()


if __name__ == "__main__":
    main()
