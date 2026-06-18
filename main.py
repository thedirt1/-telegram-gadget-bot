import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters, ConversationHandler
)

TOKEN = os.getenv("TOKEN")

# ================= DATABASE =================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    balance INTEGER,
    bought INTEGER
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    price INTEGER,
    photo TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS history (
    user_id INTEGER,
    item TEXT,
    price INTEGER
)
""")

conn.commit()

# ================= STATES =================
SET_BALANCE = 1

# ================= KEYBOARD =================
keyboard = ReplyKeyboardMarkup(
    [
        ["🛒 Магазин", "👤 Профіль"],
        ["🎮 Вхід в гру", "📦 Історія"]
    ],
    resize_keyboard=True
)

# ================= USER =================
def init_user(user_id):
    cur.execute("SELECT * FROM users WHERE id=?", (user_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, 1000, 0))
        conn.commit()

def get_user(user_id):
    init_user(user_id)
    cur.execute("SELECT balance, bought FROM users WHERE id=?", (user_id,))
    return cur.fetchone()

def update_user(user_id, balance=None, bought=None):
    bal, b = get_user(user_id)

    balance = bal if balance is None else balance
    bought = b if bought is None else bought

    cur.execute("UPDATE users SET balance=?, bought=? WHERE id=?", (balance, bought, user_id))
    conn.commit()

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    init_user(update.message.from_user.id)
    await update.message.reply_text("🛒 Вітаю в маркетплейсі!", reply_markup=keyboard)

# ================= SHOP =================
async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cur.execute("SELECT * FROM products")
    items = cur.fetchall()

    if not items:
        await update.message.reply_text("📦 Магазин порожній")
        return

    for item in items:
        item_id, name, price, photo = item

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🛒 Купити {price}€", callback_data=f"buy_{item_id}")]
        ])

        await update.message.reply_photo(
            photo=photo,
            caption=f"📱 {name}\n💰 {price}€",
            reply_markup=kb
        )

# ================= BUY =================
async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    product_id = int(query.data.split("_")[1])

    cur.execute("SELECT name, price FROM products WHERE id=?", (product_id,))
    product = cur.fetchone()

    if not product:
        await query.answer("❌ Товар не знайдено", show_alert=True)
        return

    name, price = product
    balance, bought = get_user(user_id)

    if balance < price:
        await query.answer("❌ Недостатньо балансу", show_alert=True)
        return

    balance -= price
    bought += 1

    update_user(user_id, balance, bought)

    cur.execute("INSERT INTO history VALUES (?, ?, ?)", (user_id, name, price))
    conn.commit()

    await query.answer("✅ Куплено!", show_alert=True)

# ================= PROFILE =================
async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    balance, bought = get_user(user_id)

    await update.message.reply_text(
        f"👤 Профіль\n\n💰 Баланс: {balance}€\n🛒 Куплено: {bought}"
    )

# ================= HISTORY =================
async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    cur.execute("SELECT item, price FROM history WHERE user_id=?", (user_id,))
    rows = cur.fetchall()

    if not rows:
        await update.message.reply_text("📦 Порожньо")
        return

    msg = "📦 Історія:\n\n"
    for r in rows:
        msg += f"{r[0]} | {r[1]}€\n"

    await update.message.reply_text(msg)

# ================= ENTER GAME (SET BALANCE) =================
async def enter_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 Введи свій баланс:")
    return SET_BALANCE

async def set_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    try:
        balance = int(update.message.text)
    except:
        await update.message.reply_text("❌ Введи число")
        return SET_BALANCE

    cur.execute("""
        INSERT OR REPLACE INTO users (id, balance, bought)
        VALUES (?, ?, COALESCE((SELECT bought FROM users WHERE id=?), 0))
    """, (user_id, balance, user_id))

    conn.commit()

    await update.message.reply_text(f"✅ Баланс встановлено: {balance}€")
    return ConversationHandler.END

# ================= MENU =================
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🛒 Магазин":
        await shop(update, context)

    elif text == "👤 Профіль":
        await profile(update, context)

    elif text == "📦 Історія":
        await history(update, context)

# ================= APP =================
app = Application.builder().token(TOKEN).build()

conv = ConversationHandler(
    entry_points=[MessageHandler(filters.TEXT & filters.Regex("🎮 Вхід в гру"), enter_game)],
    states={
        SET_BALANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_balance)],
    },
    fallbacks=[]
)

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu))
app.add_handler(MessageHandler(filters.TEXT & filters.Regex("🛒 Магазин"), shop))
app.add_handler(CallbackQueryHandler(buy))
app.add_handler(conv)

app.run_polling()
