from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import re

# =========================
# CONFIG
# =========================
client_ai = import os
client_ai = OpenAI(api_key=os.getenv("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"))

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name(
    "credentials.json",
    scope
)

client = gspread.authorize(creds)
sheet = client.open("Our fatfat wallets").worksheet("Raw_Data")

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
    "dbs women"
]

# =========================
# CATEGORY ENGINE
# =========================
def get_category(text):
    text_lower = text.lower()

    # =========================
    # 🥗 DINING
    # =========================
    dining_keywords = [
        "food", "eat", "meal", "restaurant", "cafe",
        "coffee", "tea", "bubble tea", "boba",
        "rice", "noodle", "ramen", "sushi",
        "burger", "pizza", "chicken", "mala",
        "hotpot", "hawker", "breakfast", "lunch",
        "dinner", "salad", "bento", "sandwich",
        "bakery", "dessert", "ice cream"
    ]

    if any(w in text_lower for w in dining_keywords):
        return "Dining"

    # =========================
    # 🥦 GROCERIES
    # =========================
    grocery_keywords = [
        "groceries", "grocery", "supermarket",
        "ntuc", "fairprice", "sheng siong", "giant",
        "cold storage"
    ]

    if any(w in text_lower for w in grocery_keywords):
        return "Groceries"

    # =========================
    # 🛍️ SHOPPING (FIXED + SHOPEE SUPPORT)
    # =========================
    shopping_keywords = [
        "shopee", "lazada", "amazon",
        "online order", "purchase", "cart",
        "shop", "checkout",

        "zara", "uniqlo", "h&m",
        "clothes", "shirt", "pants", "dress",
        "shoes", "bag", "handbag",

        "skincare", "makeup", "perfume",
        "electronics", "phone", "gadget"
    ]

    if any(w in text_lower for w in shopping_keywords):
        return "Shopping"

    # =========================
    # ✈️ TRAVEL
    # =========================
    if any(w in text_lower for w in [
        "flight", "air ticket", "hotel", "airbnb",
        "stay", "booking", "agoda", "trip.com", "trip"
    ]):
        return "Travel"

    # =========================
    # 🚕 TRANSPORT
    # =========================
    if any(w in text_lower for w in ["grab", "mrt", "bus", "taxi"]):
        return "Transport"

    # =========================
    # 🎮 ENTERTAINMENT
    # =========================
    if any(w in text_lower for w in [
        "netflix", "spotify", "movie", "cinema", "shinee",
        "concert", "ktv", "theme park", "game"
    ]):
        return "Entertainment"

    # =========================
    # 🧠 AI FALLBACK
    # =========================
    try:
        response = client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": """
Classify into:
Dining, Groceries, Shopping, Transport, Travel, Entertainment, Bills, Others.

Rules:
- food = Dining
- supermarket = Groceries
- shopee/lazada = Shopping
- flight/hotel = Travel
- grab/mrt = Transport
"""
                },
                {"role": "user", "content": text}
            ],
            max_tokens=10
        )

        category = response.choices[0].message.content.strip()

        # =========================
        # 🛡️ SAFETY OVERRIDE
        # =========================
        food_signals = [
            "ramen","sushi","rice","noodle","mala","hotpot",
            "coffee","tea","cafe","food","eat","salad","bento"
        ]

        if category == "Others" and any(w in text_lower for w in food_signals):
            return "Dining"

        return category

    except:
        return "Others"

# =========================
# HANDLER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    text_lower = text.lower()
    user = update.message.from_user.first_name

    try:
        # AMOUNT
        match = re.search(r"(\d+(\.\d+)?)", text)
        if not match:
            raise ValueError("No amount found")

        amount = float(match.group())

        # SPLIT
        is_shared = "shared" in text_lower or "split" in text_lower
        split_flag = "yes" if is_shared else "no"
        user_field = "shared" if is_shared else user

        # PAYMENT
        payment = "cash"
        for m in PAYMENT_METHODS:
            if m in text_lower:
                payment = m
                break

        # CLEAN NAME
        clean_text = text_lower
        clean_text = re.sub(r"(\d+(\.\d+)?)", "", clean_text)

        for m in PAYMENT_METHODS:
            clean_text = clean_text.replace(m, "")

        clean_text = clean_text.replace("shared", "")
        clean_text = clean_text.replace("split", "")

        name = clean_text.strip()

        # CATEGORY
        category = get_category(name)

        print("TEXT:", text)
        print("NAME:", name)
        print("CATEGORY:", category)

        # SAVE TO SHEET
        sheet.append_row([
            datetime.now().strftime("%Y-%m-%d"),
            user_field,
            name,
            category,
            amount,
            payment,
            split_flag
        ])

        await update.message.reply_text(
            f"✅ Added: {name}\n💰 ${amount}\n📂 {category}\n💳 {payment}\n🔁 Split: {split_flag}"
        )

    except Exception as e:
        print("ERROR:", e)
        await update.message.reply_text(
            "❌ Format: coffee 5 cash / shopee dress 20 / ramen 12 split"
        )

# =========================
# SUMMARY
# =========================
async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    records = sheet.get_all_records()

    total = sum(float(r["Amount"]) for r in records)

    await update.message.reply_text(f"📊 Total Spend: ${total:.2f}")

# =========================
# RUN BOT
# =========================
app = ApplicationBuilder()..token(os.getenv("AAGWYwoTGXCESRtncIUQw9XQiiaS6NAFoZQ)).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CommandHandler("summary", summary))

app.run_polling()