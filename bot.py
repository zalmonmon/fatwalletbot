import os
import re
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

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN environment variable")

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

creds = ServiceAccountCredentials.from_json_keyfile_name(
    "credentials.json",
    scope,
)
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

    dining_keywords = [
        "food", "eat", "meal", "restaurant", "cafe", "kopi",
        "coffee", "tea", "bubble tea", "boba", "juice",
        "rice", "noodle", "ramen", "sushi", "burger", "pizza",
        "chicken rice", "mala", "hotpot", "steamboat", "kbbq",
        "hawker", "breakfast", "lunch", "dinner", "brunch",
        "salad", "sandwich", "bento", "bakery", "dessert",
        "ice cream", "cake", "toast", "yakun", "luckin", "chagee",
        "stuff'd", "caifan", "nasi lemak", "nasi padang", "ytf",
    ]
    if any(word in text_lower for word in dining_keywords):
        return "Dining"

    grocery_keywords = [
        "groceries", "grocery", "supermarket", "ntuc", "fairprice",
        "sheng siong", "giant", "cold storage", "wet market",
        "market", "bread", "milk", "eggs", "vegetable", "vegetables",
        "fruit", "fruits", "tofu", "yogurt", "yoghurt", "fish",
        "beef", "pork", "snacks", "oil", "sauce", "seasoning",
    ]
    if any(word in text_lower for word in grocery_keywords):
        return "Groceries"

    shopping_keywords = [
        "shopee", "lazada", "amazon", "cart", "checkout", "order",
        "online order", "purchase", "zara", "uniqlo", "h&m",
        "clothes", "shirt", "pants", "dress", "shoes", "bag",
        "handbag", "skincare", "makeup", "perfume", "electronics",
        "phone", "gadget", "accessories",
    ]
    if any(word in text_lower for word in shopping_keywords):
        return "Shopping"

    travel_keywords = [
        "flight", "air ticket", "hotel", "airbnb", "stay",
        "accommodation", "booking", "trip", "travel insurance",
        "airport transfer",
    ]
    if any(word in text_lower for word in travel_keywords):
        return "Travel"

    transport_keywords = [
        "grab", "mrt", "bus", "taxi", "gojek", "train", "lrt",
        "parking", "erp", "petrol",
    ]
    if any(word in text_lower for word in transport_keywords):
        return "Transport"

    entertainment_keywords = [
        "netflix", "spotify", "movie", "cinema", "concert", "ktv",
        "karaoke", "game", "steam", "playstation", "arcade",
        "bowling", "theme park",
    ]
    if any(word in text_lower for word in entertainment_keywords):
        return "Entertainment"

    bills_keywords = [
        "electricity", "water bill", "internet", "wifi", "broadband",
        "phone bill", "telco", "insurance", "rent", "tax", "utilities",
        "subscription",
    ]
    if any(word in text_lower for word in bills_keywords):
        return "Bills"

    # AI fallback only if key exists
    if client_ai:
        try:
            response = client_ai.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Classify this expense into exactly one category: "
                            "Dining, Groceries, Shopping, Transport, Travel, "
                            "Entertainment, Bills, Others. "
                            "Return only the category name."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                max_tokens=10,
            )
            category = response.choices[0].message.content.strip()

            allowed = {
                "Dining", "Groceries", "Shopping", "Transport",
                "Travel", "Entertainment", "Bills", "Others"
            }
            if category in allowed:
                return category

        except Exception as e:
            print("AI category fallback error:", e)

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

        print(
            {
                "text": text,
                "name": name,
                "category": category,
                "amount": amount,
                "payment": payment,
                "split": split_flag,
                "user": user_field,
            }
        )

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
            "Examples:\n"
            "coffee 5 uob lady\n"
            "ramen 12 cash\n"
            "shopee order 20 maybank\n"
            "dinner 50 grab split"
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
