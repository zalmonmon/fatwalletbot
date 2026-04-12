import os
import re
from datetime import datetime

from openai import OpenAI
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# =========================
# CONFIG
# =========================
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

# ✅ make sure this matches your sheet tab EXACTLY
sheet = client.open("1alH2j7pRYokrNDsRVltsFF161cbjHPIqa-8sG3cxFZc").worksheet("raw_data")

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

    # 🍜 DINING (STRONG)
    dining_keywords = [
        "food","eat","meal","restaurant","cafe",
        "coffee","tea","boba","bubble tea",
        "rice","noodle","ramen","sushi",
        "burger","pizza","chicken","mala","hotpot",
        "breakfast","lunch","dinner",
        "salad","sandwich","bento",
        "dessert","ice cream","cake"
    ]
    if any(w in text_lower for w in dining_keywords):
        return "Dining"

    # 🥦 GROCERIES
    grocery_keywords = [
        "groceries","grocery","supermarket",
        "ntuc","fairprice","sheng siong","giant",
        "cold storage","wet market",
        "milk","eggs","bread","vegetable","fruit",
        "tofu","yogurt","meat","fish","snacks","rice"
    ]
    if any(w in text_lower for w in grocery_keywords):
        return "Groceries"

    # 🛍️ SHOPPING (FIXED)
    shopping_keywords = [
        "shopee","lazada","amazon",
        "online","checkout","cart","order",
        "zara","uniqlo","h&m",
        "clothes","shirt","pants","dress",
        "shoes","bag",
        "skincare","makeup","perfume",
        "electronics","phone","gadget"
    ]
    if any(w in text_lower for w in shopping_keywords):
        return "Shopping"

    # ✈️ TRAVEL
    if any(w in text_lower for w in [
        "flight","air ticket","hotel","airbnb",
        "booking","trip","stay"
    ]):
        return "Travel"

    # 🚕 TRANSPORT
    if any(w in text_lower for w in ["grab","mrt","bus","taxi"]):
        return "Transport"

    # 🎮 ENTERTAINMENT
    if any(w in text_lower for w in [
        "netflix","spotify","movie","cinema",
        "concert","ktv","game"
    ]):
        return "Entertainment"

    # 🤖 AI FALLBACK
    try:
        response = client_ai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": """
Classify into:
Dining, Groceries, Shopping, Transport, Travel, Entertainment, Bills, Others.

Food = Dining
Supermarket = Groceries
Shopee/Lazada = Shopping
Flights/Hotels = Travel
Grab/MRT = Transport

Return only category name.
"""
                },
                {"role": "user", "content": text}
            ],
            max_tokens=10
        )

        category = response.choices[0].message.content.strip()

        # safety override
        if category == "Others" and any(w in text_lower for w in ["food","eat","coffee","ramen","salad"]):
            return "Dining"

        return category

    except:
        return "Others"

# =========================
# MESSAGE HANDLER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    text_lower = text.lower()
    user = update.message.from_user.first_name

    try:
        # 💰 amount
        match = re.search(r"(\d+(\.\d+)?)", text)
        if not match:
            raise ValueError("No amount")

        amount = float(match.group())

        # 👥 split
        is_shared = "shared" in text_lower or "split" in text_lower
        split_flag = "yes" if is_shared else "no"
        user_field = "shared" if is_shared else user

        # 💳 payment
        payment = "cash"
        for m in PAYMENT_METHODS:
            if m in text_lower:
                payment = m
                break

        # 🧹 clean name
        clean_text = re.sub(r"(\d+(\.\d+)?)", "", text_lower)

        for m in PAYMENT_METHODS:
            clean_text = clean_text.replace(m, "")

        clean_text = clean_text.replace("shared", "").replace("split", "")

        name = clean_text.strip()

        # 📂 category
        category = get_category(name)

        print("DEBUG:", name, category)

        # 📊 save to sheet
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
            f"✅ {name}\n💰 ${amount}\n📂 {category}\n💳 {payment}\n🔁 {split_flag}"
        )

    except Exception as e:
        print("ERROR:", e)
        await update.message.reply_text(
            "❌ Format: coffee 5 cash / ramen 12 split / shopee 20"
        )

# =========================
# SUMMARY
# =========================
async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    records = sheet.get_all_records()
    total = sum(float(r["Amount"]) for r in records)

    await update.message.reply_text(f"📊 Total Spend: ${total:.2f}")

# =========================
# RUN BOT (FIXED)
# =========================
app = ApplicationBuilder().token(os.getenv("8635228440:AAH7wonBDto1uyDA9B9XEq8aEf-nYxUdatc")).build()

app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CommandHandler("summary", summary))

app.run_polling()
