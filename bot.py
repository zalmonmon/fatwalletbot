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
# CONFIG
# =========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
print("AI ENABLED:", bool(OPENAI_API_KEY))
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

    hard_rules = {
        "Dining": [
            "food","eat","restaurant","cafe","kopitiam","kopi","kopi o",
            "teh","teh o","jolibee","mcd","coffee","boba","ramen","sushi",
            "dinner","lunch","mala","xxhn","ijooz","onigiri","dabba",
            "nasi","rice","soup","grains","stuffd","porridge","brunch",
            "caifan","cai fan","yakun","ya kun","luckin","chagee",
            "liho","gong cha","koi","playmade","grabfood","foodpanda","matcha",
        ],

        "Groceries": [
            "ntuc","fairprice","sheng siong","giant","grocery",
            "milk","eggs","vegetable","cold storage","fruit","flour",
            "donki","redmart","market","wet market","supermarket"
        ],

        "Shopping": [
            "shopee","lazada","amazon","zara","uniqlo","clothes",
            "skincare","rosebeauty","lovet","ssd","makeup",
            "taobao","shein","watsons","guardian","sephora",
            "ikea","muji","miniso","decathlon"
        ],

        "Travel": [
            "flight","hotel","airbnb","trip","trip.com","traveloka",
            "agoda","klook","airport","holiday","luggage"
        ],

        "Transport": [
            "grab","mrt","bus","taxi","erp","petrol",
            "gojek","tada","parking","ezlink","simplygo"
        ],

        "Entertainment": [
            "netflix","spotify","movie","concert","maple","maplestory"
            "youtube","shinee","cinema","steam","game"
        ],

        "Bills": [
            "bill","rent","insurance","wifi","telco",
            "gomo","giga","tax","utilities","sp bill",
            "electricity","water","subscription"
        ],
    }

    # Hard rules first
    for category, keywords in hard_rules.items():
        if any(word in text_lower for word in keywords):
            return category

    # Smart AI fallback
    if client_ai:
        try:
            response = client_ai.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """
You classify Singapore personal expenses.

Return exactly ONE category:
Dining, Groceries, Shopping, Transport, Travel, Entertainment, Bills, Others.

Rules:
- Hawker food / drinks / restaurants / cafes = Dining
- Supermarket / ingredients / home food = Groceries
- Shopee / Lazada / retail / beauty / clothes = Shopping
- Grab / MRT / petrol / parking = Transport
- Flight / hotel / overseas trip = Travel
- Netflix / cinema / games / concerts = Entertainment
- Utilities / rent / telco / insurance = Bills

Return only category name.
"""
                    },
                    {"role": "user", "content": text}
                ],
                max_tokens=10,
                temperature=0
            )

            category = response.choices[0].message.content.strip()

            allowed = {
                "Dining","Groceries","Shopping","Transport",
                "Travel","Entertainment","Bills","Others"
            }

            if category in allowed:
                return category

        except Exception as e:
            print("AI category fallback error:", e)

    return "Others"# 
=========================
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
    
CATEGORIES = [
    "Dining",
    "Groceries",
    "Shopping",
    "Transport",
    "Travel",
    "Entertainment",
    "Bills",
    "Others",
]

pending_expenses = {}
# =========================
# MESSAGE HANDLER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    text_lower = text.lower()
    user = update.message.from_user.first_name or "Unknown"
    chat_id = update.message.chat_id

    try:
        amount = extract_amount(text)
        is_shared = ("shared" in text_lower) or ("split" in text_lower)
        split_flag = "yes" if is_shared else "no"
        user_field = "shared" if is_shared else user
        payment = detect_payment(text_lower)
        name = clean_name(text_lower)
        category = get_category(name)

        if category != "Others":
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
            return

        pending_expenses[chat_id] = {
            "user_field": user_field,
            "name": name,
            "amount": amount,
            "payment": payment,
            "split_flag": split_flag,
        }

        keyboard = [
            [
                InlineKeyboardButton("Dining", callback_data="cat:Dining"),
                InlineKeyboardButton("Groceries", callback_data="cat:Groceries"),
            ],
            [
                InlineKeyboardButton("Shopping", callback_data="cat:Shopping"),
                InlineKeyboardButton("Transport", callback_data="cat:Transport"),
            ],
            [
                InlineKeyboardButton("Travel", callback_data="cat:Travel"),
                InlineKeyboardButton("Entertainment", callback_data="cat:Entertainment"),
            ],
            [
                InlineKeyboardButton("Bills", callback_data="cat:Bills"),
                InlineKeyboardButton("Others", callback_data="cat:Others"),
            ],
        ]

        await update.message.reply_text(
            f"Select category for: {name}\n💰 ${amount:.2f}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    except Exception as e:
        print("handle_message error:", e)
        await update.message.reply_text(
            "❌ Could not parse.\nExample: coffee 5 uob lady"
        )

async def category_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = query.message.chat_id
    category = query.data.replace("cat:", "")

    expense = pending_expenses.get(chat_id)

    if not expense:
        await query.edit_message_text("❌ No pending expense found. Please key in again.")
        return

    sheet.append_row([
        datetime.now().strftime("%Y-%m-%d"),
        expense["user_field"],
        expense["name"],
        category,
        expense["amount"],
        expense["payment"],
        expense["split_flag"],
    ])

    await query.edit_message_text(
        f"✅ Added: {expense['name']}\n"
        f"💰 ${expense['amount']:.2f}\n"
        f"📂 {category}\n"
        f"💳 {expense['payment']}\n"
        f"🔁 Split: {expense['split_flag']}"
    )

    del pending_expenses[chat_id]

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
app.add_handler(CallbackQueryHandler(category_button))
app.run_polling()
