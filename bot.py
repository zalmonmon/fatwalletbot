import os
import re
import json
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from openai import OpenAI
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# =========================
# CONFIG
# =========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN")

if not GOOGLE_CREDENTIALS:
    raise ValueError("Missing GOOGLE_CREDENTIALS")

client_ai = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

GOOGLE_SHEET_ID = "1alH2j7pRYokrNDsRVltsFF161cbjHPIqa-8sG3cxFZc"
WORKSHEET_NAME = "raw_data"

# =========================
# GOOGLE SHEETS SETUP
# =========================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

creds_dict = json.loads(GOOGLE_CREDENTIALS)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(GOOGLE_SHEET_ID).worksheet(WORKSHEET_NAME)

# =========================
# PAYMENT METHODS
# =========================
PAYMENT_METHODS = [
    "cash",
    "paylah",
    "shopback",
    "uob lady",
    "citi",
    "maybank",
    "uob ppv",
    "dbs women",
]

# =========================
# CATEGORY ENGINE
# =========================
def get_category(text: str) -> str:
    text_lower = text.lower().strip()

    if any(word in text_lower for word in ["food","eat","restaurant","cafe","coffee","boba","ramen","sushi","dinner","lunch","mala","nasi","rice","soup","grains","stuffd","porridge","brunch"]):
        return "Dining"

    if any(word in text_lower for word in ["ntuc","fairprice","sheng siong","giant","grocery","milk","eggs","vegetable","cold storage","fruit"]):
        return "Groceries"

    if any(word in text_lower for word in ["shopee","lazada","amazon","zara","uniqlo","clothes","skincare","lovet","SSD","makeup"]):
        return "Shopping"

    if any(word in text_lower for word in ["flight","hotel","airbnb","trip","trip.com","traveloka","agoda"]):
        return "Travel"

    if any(word in text_lower for word in ["grab","mrt","bus","taxi","erp","petrol"]):
        return "Transport"

    if any(word in text_lower for word in ["netflix","spotify","movie","concert","maple","youtube","shinee"]):
        return "Entertainment"

    if any(word in text_lower for word in ["bill","rent","insurance","wifi","telco","gomo","giga","tax"]):
        return "Bills"

    return "Others"

# =========================
# HELPERS
# =========================
def extract_amount(text: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        raise ValueError("No amount found")
    return float(match.group(1))

def detect_payment(text_lower: str) -> str:
    for method in PAYMENT_METHODS:
        if method in text_lower:
            return method
    return "cash"

def clean_name(text_lower: str) -> str:
    cleaned = re.sub(r"(\d+(?:\.\d+)?)", "", text_lower)

    for method in PAYMENT_METHODS:
        cleaned = cleaned.replace(method, "")

    cleaned = cleaned.replace("shared", "")
    cleaned = cleaned.replace("split", "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        raise ValueError("Expense name is empty")
    return cleaned

# =========================
# MESSAGE HANDLER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    text_lower = text.lower()
    user = update.message.from_user.first_name or "Unknown"

    try:
        amount = extract_amount(text)
        is_shared = ("shared" in text_lower) or ("split" in text_lower)
        split_flag = "yes" if is_shared else "no"
        user_field = "shared" if is_shared else user
        payment = detect_payment(text_lower)
        name = clean_name(text_lower)
        category = get_category(name)

        sheet.append_row([
            datetime.now().strftime("%Y-%m-%d"),
            user_field,
            name,
            category,
            amount,
            payment,
            split_flag,
        ])

        await update.message.reply_text(
            f"✅ Added: {name}\n"
            f"💰 ${amount:.2f}\n"
            f"📂 {category}\n"
            f"💳 {payment}\n"
            f"🔁 Split: {split_flag}"
        )

    except Exception as e:
        print("handle_message error:", e)
        await update.message.reply_text(
            "❌ Could not parse.\n"
            "Example: coffee 5 uob lady"
        )

# =========================
# SUMMARY
# =========================
async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        records = sheet.get_all_records()
        total = sum(float(row.get("Amount", 0) or 0) for row in records)
        await update.message.reply_text(f"📊 Total Spend: ${total:.2f}")
    except Exception as e:
        print("summary error:", e)
        await update.message.reply_text("❌ Could not generate summary.")

# =========================
# RUN BOT
# =========================
app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

app.add_handler(CommandHandler("summary", summary))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app.run_polling()
