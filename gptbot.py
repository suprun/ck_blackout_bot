import os
import asyncio
import aiosqlite
import nest_asyncio
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters,
)

# === .env ===
load_dotenv()

# === Config ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.getenv("DATABASE_PATH", "users.db")
MINIAPP_URL = os.getenv("MINIAPP_URL", "https://cherkasyoblenergo.com/static/perelik-gpv")

QUEUE_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]
GROUP_LINKS = {f"{i}_{j}": f"https://t.me/ck_blackout_{i}_{j}" for i in range(1, 7) for j in (1, 2)}

# === Logging ===
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# === DB ===
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                start_time TEXT,
                is_premium INTEGER DEFAULT 0
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_queues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                queue INTEGER,
                subqueue INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            """
        )
        await db.commit()

# === Keyboards ===

def start_keyboard():
    rows = [[InlineKeyboardButton(f"{QUEUE_EMOJI[i]} Черга", callback_data=f"queue_{i+1}")] for i in range(6)]
    rows.append([InlineKeyboardButton("🤷‍♂️ Я не знаю", callback_data="unknown_queue")])
    return InlineKeyboardMarkup(rows)

def sub_keyboard(queue: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Ⅰ підчерга", callback_data=f"sub_{queue}_1"),
            InlineKeyboardButton("Ⅱ підчерга", callback_data=f"sub_{queue}_2"),
        ],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")],
    ])

def subscription_keyboard(key: str):
    group_url = GROUP_LINKS.get(key, "#")
    queue, sub = key.split("_")
    queue_label = f"{QUEUE_EMOJI[int(queue)-1]} черга {'Ⅰ' if sub=='1' else 'Ⅱ'} підчерга"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Сповіщення в каналі", url=group_url)],
        [InlineKeyboardButton("💫 Сповіщення в боті", callback_data=f"personal_{key}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_queue_{queue}"), InlineKeyboardButton("🏠 Головне меню", callback_data="main_menu")],
        
    ])

def personal_info_keyboard(key: str, queue_label: str, group_url: str, back_cb: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💬 Отримувати сповіщення в каналі {queue_label}", url=group_url)],
        [InlineKeyboardButton("💫 Отримати сповіщення в боті за 10 ⭐️", callback_data=f"buy_{key}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=back_cb), InlineKeyboardButton("🏠 Головне меню", callback_data="main_menu")],
    ])

def unknown_keyboard(back_cb: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Знайти адресу (Mini App)", web_app={"url": MINIAPP_URL})],
        [InlineKeyboardButton("⬅️ Назад", callback_data=back_cb)],
    ])

def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [["📊 Мої черги", "💫 Premium"], ["🏠 Головне меню"]], resize_keyboard=True, one_time_keyboard=False
    )

# === Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name, start_time) VALUES (?, ?, ?, ?)",
            (user.id, user.username, user.first_name, datetime.now().isoformat()),
        )
        await db.commit()

    context.user_data.pop("last_queue_selection", None)

    await update.message.reply_text(f"👋 Вітаю, {user.first_name or 'друже'}!\n⬇️ Оберіть свою чергу:")
    await update.message.reply_text("⬇️ Оберіть свою чергу:", reply_markup=start_keyboard())

async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📋 Головне меню:", reply_markup=main_menu_keyboard())

async def queue_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    queue = int(query.data.split("_")[1])
    context.user_data["last_queue_selection"] = f"back_to_queue_{queue}"
    await query.edit_message_text(
        f"📊 Ви обрали {QUEUE_EMOJI[queue-1]} чергу. Тепер виберіть підчергу:",
        reply_markup=sub_keyboard(queue),
    )

async def sub_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, queue, sub = query.data.split("_")
    key = f"{queue}_{sub}"
    context.user_data["last_queue_selection"] = f"back_to_queue_{queue}"
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT is_premium FROM users WHERE user_id=?", (query.from_user.id,))
        user_row = await cur.fetchone()
        is_premium = user_row and user_row[0] == 1
        if not is_premium:
            await db.execute("DELETE FROM user_queues WHERE user_id=?", (query.from_user.id,))
        await db.execute(
            "INSERT INTO user_queues (user_id, queue, subqueue) VALUES (?, ?, ?)",
            (query.from_user.id, queue, sub),
        )
        await db.commit()
    context.user_data["last_message_callback"] = f"sub_{queue}_{sub}"
    await query.edit_message_text(
        f"🔌 Ви обрали {QUEUE_EMOJI[int(queue)-1]} чергу {'Ⅰ' if sub=='1' else 'Ⅱ'} підчергу.",
        reply_markup=subscription_keyboard(key),
    )

async def personal_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.split("personal_")[1]
    queue, sub = key.split("_")
    queue_label = f"{QUEUE_EMOJI[int(queue)-1]} черга {'Ⅰ' if sub=='1' else 'Ⅱ'} підчерга"
    group_url = GROUP_LINKS.get(key, '#')
    description = (
        f"  ✨ Переваги персональних сповіщень в боті:\n\n"
        f"⏱️ Налаштування сповіщень за 5/10/15 або 20 хвилин до відключення\n"
        f"💬 Сповіщення про декілька черг в одному чаті\n"
        f"🌙 Вимкнення сповіщень у нічний час\n"
        f"🔕 Без спаму, лише корисна інформація\n"
        f"🙏 Ви підтримуєте цей проєкт. (одноразовий платіж 10 ⭐️ ≈10₴)\n\n"
        f"або\n\n"
        f"• 💬 Приєднайтесь до каналу «Графік відключень {queue_label}» та отримуйте сповіщення безкоштовно.\n\n"
    )
    back_cb = context.user_data.get("last_message_callback", f"sub_{queue}_{sub}")
    await query.edit_message_text(description, reply_markup=personal_info_keyboard(key, queue_label, group_url, back_cb))

async def my_queues(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT queue, subqueue FROM user_queues WHERE user_id=?", (user_id,))
        rows = await cur.fetchall()
    if not rows:
        await update.message.reply_text("ℹ️ Ви ще не обрали жодної черги.")
        return
    text = "📊 Ваші черги:\n" + "\n".join([
        f"{QUEUE_EMOJI[q-1]} {q} черга {'Ⅰ' if s==1 else 'Ⅱ'}" for q, s in rows
    ])
    await update.message.reply_text(text, reply_markup=main_menu_keyboard())

async def unknown_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    back_cb = context.user_data.get("last_queue_selection", "back_to_start")
    text = "🔍 Не знаєте свою чергу? Знайдіть адресу у Mini App і поверніться назад, щоб обрати чергу/підчергу."
    await query.edit_message_text(text, reply_markup=unknown_keyboard(back_cb))

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("last_queue_selection", None)
    await query.edit_message_text("⬇️ Оберіть свою чергу:", reply_markup=start_keyboard())

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.split("buy_")[1]
    prices = [LabeledPrice("Персональні сповіщення", 10)]
    await context.bot.send_invoice(
        chat_id=query.from_user.id,
        title="⭐️ Персональні сповіщення",
        description="Отримайте персональні сповіщення у боті. Вартість 10⭐️",
        payload=f"stars_{key}",
        currency="XTR",
        prices=prices,
        provider_token="",
        start_parameter="personal_alerts",
    )

async def toggle_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT is_premium FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT INTO users (user_id, username, first_name, start_time, is_premium) VALUES (?, ?, ?, ?, 1)",
                (user_id, update.effective_user.username, update.effective_user.first_name, datetime.now().isoformat()),
            )
            status = True
        else:
            new_status = 0 if row[0] == 1 else 1
            await db.execute("UPDATE users SET is_premium=? WHERE user_id=?", (new_status, user_id))
            status = bool(new_status)
        await db.commit()
    msg = "✅ Premium увімкнено" if status else "❌ Premium вимкнено"
    await update.message.reply_text(msg, reply_markup=main_menu_keyboard())

# === Main ===
async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задано. Додайте його в .env або змінні середовища.")
        return
    await init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("prem", toggle_premium))
    app.add_handler(CommandHandler("myqueues", my_queues))
    app.add_handler(CallbackQueryHandler(queue_choice, pattern="^queue_"))
    app.add_handler(CallbackQueryHandler(sub_choice, pattern="^sub_"))
    app.add_handler(CallbackQueryHandler(personal_info, pattern="^personal_"))
    app.add_handler(CallbackQueryHandler(unknown_queue, pattern="^unknown_queue$"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    app.add_handler(CallbackQueryHandler(buy_premium, pattern="^buy_"))
    app.add_handler(CallbackQueryHandler(menu_command, pattern="^main_menu$"))

    logger.info("Бот запущено з меню, /myqueues і повною підтримкою Premium")
    await app.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())