import os
import re
import json
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# =========================
# NEW: FLASK FOR RENDER
# =========================
from flask import Flask
import threading

web_app = Flask(__name__)

@web_app.route("/")
def home():
    return "Bot is running"

# =========================
# CONFIG
# =========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")

print("AI ENABLED:", bool(OPENAI_API_KEY))

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
    "cash", "paylah", "shopback", "uob lady", "citi",
    "maybank", "uob ppv", "dbs women",
]

# =========================
# CATEGORY ENGINE
# =========================
def get_category(text: str) -> str:
    text_lower = text.lower().strip()

    hard_rules = {
        "Dining": ["food","eat","restaurant","cafe","kopitiam","coffee","mcd","ramen","sushi"],
        "Groceries": ["ntuc","fairprice","sheng siong","giant","grocery","milk","eggs"],
        "Shopping": ["shopee","lazada","amazon","zara","uniqlo","clothes","makeup","sephora"],
        "Travel": ["flight","hotel","airbnb","trip","agoda","klook","airport"],
        "Transport": ["grab","mrt","bus","taxi","petrol","parking"],
        "Entertainment": ["netflix","spotify","movie","game","cinema","youtube"],
        "Bills": ["bill","rent","wifi","telco","insurance","utilities"],
    }

    for category, keywords in hard_rules.items():
        if any(k in text_lower for k in keywords):
            return category

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

    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        raise ValueError("Expense name empty")

    return cleaned

pending_expenses = {}

# =========================
# TELEGRAM HANDLERS
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    text_lower = text.lower()

    user = update.message.from_user.first_name or "Unknown"
    chat_id = update.message.chat_id

    try:
        amount = extract_amount(text)
        payment = detect_payment(text_lower)
        name = clean_name(text_lower)
        category = get_category(name)

        if category != "Others":
            sheet.append_row([
                datetime.now().strftime("%Y-%m-%d"),
                user,
                name,
                category,
                amount,
                payment,
            ])

            await update.message.reply_text(f"✅ Added {name} (${amount}) - {category}")
            return

        pending_expenses[chat_id] = {
            "user": user,
            "name": name,
            "amount": amount,
            "payment": payment,
        }

        keyboard = [
            [
                InlineKeyboardButton("Dining", callback_data="Dining"),
                InlineKeyboardButton("Groceries", callback_data="Groceries"),
            ],
            [
                InlineKeyboardButton("Shopping", callback_data="Shopping"),
                InlineKeyboardButton("Transport", callback_data="Transport"),
            ],
            [
                InlineKeyboardButton("Travel", callback_data="Travel"),
                InlineKeyboardButton("Entertainment", callback_data="Entertainment"),
            ],
            [
                InlineKeyboardButton("Bills", callback_data="Bills"),
                InlineKeyboardButton("Others", callback_data="Others"),
            ],
        ]

        await update.message.reply_text(
            f"Select category for {name} (${amount})",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    except Exception as e:
        print(e)
        await update.message.reply_text("❌ Could not parse expense")

async def category_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    category = query.data

    expense = pending_expenses.get(chat_id)

    if not expense:
        await query.edit_message_text("❌ No pending expense")
        return

    sheet.append_row([
        datetime.now().strftime("%Y-%m-%d"),
        expense["user"],
        expense["name"],
        category,
        expense["amount"],
        expense["payment"],
    ])

    await query.edit_message_text(f"✅ Added {expense['name']} - {category}")
    del pending_expenses[chat_id]

# =========================
# BOT SETUP
# =========================
telegram_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
telegram_app.add_handler(CallbackQueryHandler(category_button))

def run_bot():
    telegram_app.run_polling()

# =========================
# START EVERYTHING (FIXED FOR RENDER)
# =========================
if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()

    web_app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000))
    )
