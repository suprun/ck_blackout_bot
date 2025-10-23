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
    PreCheckoutQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
import aiohttp
# === .env ===
load_dotenv()

# === Config ===
BOT_TOKEN = os.getenv("BOT_START_TOKEN")
DB_PATH = os.getenv("DATABASE_PATH", "users.db")
MINIAPP_URL = os.getenv("MINIAPP_URL", "https://www.cherkasyoblenergo.com/off")
PDF_URL = os.getenv("PDF_URL", "https://storage.googleapis.com/ck_blackout_pdf/")

QUEUE_EMOJI = ["🔴1️⃣", "🟠2️⃣", "🟢3️⃣", "🔵4️⃣", "🟣5️⃣", "🟡6️⃣"]
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
                queue INTEGER,
                subqueue INTEGER
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
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")], [InlineKeyboardButton("🏠 Головне меню", callback_data="main_menu")],
    ])

def subscription_keyboard(key: str):
    group_url = GROUP_LINKS.get(key, "#")
    queue, sub = key.split("_")
    queue_label = f"{QUEUE_EMOJI[int(queue)-1]} черга {'Ⅰ' if sub=='1' else 'Ⅱ'} підчерга"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💬 Перейти в канал «{queue_label}»", url=group_url)],        
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_queue_{queue}"), InlineKeyboardButton("🏠 Головне меню", callback_data="main_menu")],[InlineKeyboardButton("💖 Підтримати проєкт", callback_data="support_project_from_sub")],
    ])

def support_keyboard(back_cb: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐️ 5", callback_data="donate_5"), InlineKeyboardButton("⭐️ 10", callback_data="donate_10")],
        [InlineKeyboardButton("⭐️ 20", callback_data="donate_20"), InlineKeyboardButton("⭐️ 50", callback_data="donate_50")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=back_cb)],
    ])

def unknown_keyboard(back_cb: str):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Знайти адресу (Mini App)", web_app={"url": MINIAPP_URL})],
        [InlineKeyboardButton("📄 Скачати графіки в PDF", callback_data="show_pdfs")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=back_cb)],
        [InlineKeyboardButton("🏠 Головне меню", callback_data="main_menu")],
    ])

def reply_main_menu():
    return ReplyKeyboardMarkup(
        [["📋 Вибрати чергу", "💬 Список каналів"], ["🔍 Знайти адресу", "ℹ️ Про бота"]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

def channels_keyboard():
    rows = []
    for key, url in GROUP_LINKS.items():
        q, s = key.split("_")
        label = f"{QUEUE_EMOJI[int(q)-1]} черга {'Ⅰ' if s=='1' else 'Ⅱ'} підчерга"
        rows.append([InlineKeyboardButton(label, url=url)])
    return InlineKeyboardMarkup(rows)

def about_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💖 Підтримати проєкт", callback_data="support_project_from_about")]
    ])

# === Handlers ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name, start_time) VALUES (?, ?, ?, ?)",
            (user.id, user.username, user.first_name, datetime.now().isoformat()),
        )
        await db.commit()

    await update.message.reply_text(
        f"👋 Вітаю, {user.first_name or 'друже'}!\nПотрібно обрати свою чергу і підчергу\n\n⬇️ Спочатку оберіть чергу:",
        reply_markup=start_keyboard(),
    )

async def queue_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    queue = int(query.data.split("_")[1])
    await query.edit_message_text(
        f"📊 Ви обрали {QUEUE_EMOJI[queue-1]} чергу. \n\nТепер виберіть підчергу:",
        reply_markup=sub_keyboard(queue),
    )

async def sub_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, queue, sub = query.data.split("_")
    key = f"{queue}_{sub}"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET queue=?, subqueue=? WHERE user_id=?",
            (queue, sub, query.from_user.id),
        )
        await db.commit()
    await query.edit_message_text(
        f"🔌 ОК, перейдіть в канал \n«{QUEUE_EMOJI[int(queue)-1]} черга {'Ⅰ' if sub=='1' else 'Ⅱ'} підчерга», \nщоб отримувати сповіщення про відключення електроенергії:",
        reply_markup=subscription_keyboard(key),
    )

async def support_project(update: Update, context: ContextTypes.DEFAULT_TYPE, back_cb="back_to_support_prev"):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🙏 Дякуємо за бажання підтримати проєкт!\nОберіть кількість зірочок:",
        reply_markup=support_keyboard(back_cb),
    )

async def donate_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    stars = query.data.split("_")[1]
    prices = [LabeledPrice(f"Підтримка проєкту на {stars}⭐️", int(stars))]
    await context.bot.send_invoice(
        chat_id=query.from_user.id,
        title="💖 Підтримати проєкт",
        description=f"Підтримка проєкту на {stars}⭐️",
        payload=f"donation_{stars}",
        currency="XTR",
        prices=prices,
        provider_token="",
        start_parameter="support_project",
    )

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stars = update.message.successful_payment.total_amount
    await update.message.reply_text(f"💖 Дякуємо за підтримку проєкту! Ви задонатили {stars}⭐️ ✨")

async def unknown_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    back_cb = "back_to_start"
    await query.edit_message_text(
        "🤷‍♂️ Не знаєте свою чергу? \nЗнайдіть свою адресу у графіку відключень:",
        reply_markup=unknown_keyboard(back_cb),
    )

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⬇️ Оберіть свою чергу:", reply_markup=start_keyboard())

async def back_to_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    queue = int(query.data.split("_")[-1])
    await query.edit_message_text(
        f"📊 Ви обрали {QUEUE_EMOJI[queue-1]} чергу. Тепер виберіть підчергу:",
        reply_markup=sub_keyboard(queue),
    )

async def back_to_support_prev(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT queue, subqueue FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
    if row and row[0] and row[1]:
        key = f"{row[0]}_{row[1]}"
        await query.edit_message_text(
            f"ОК, перейдіть в канал \n«{QUEUE_EMOJI[int(row[0])-1]} черга {'Ⅰ' if row[1]==1 else 'Ⅱ'} підчерга», \nщоб отримувати сповіщення про відключення електроенергії.",
            reply_markup=subscription_keyboard(key),
        )
    else:
        await back_to_start(update, context)

# === Головне меню ===
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.message.reply_text("📋 Головне меню:", reply_markup=reply_main_menu())
    else:
        await update.message.reply_text("📋 Головне меню:", reply_markup=reply_main_menu())

# Обробка команд меню
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "📋 Вибрати чергу":
        await update.message.reply_text("⬇️ Оберіть свою чергу:", reply_markup=start_keyboard())
    elif text == "💬 Список каналів":
        await update.message.reply_text("📢 Канали для сповіщень:", reply_markup=channels_keyboard())
    elif text == "🔍 Знайти адресу":
        await update.message.reply_text("🤷‍♂️ Не знаєте свою чергу? \nЗнайдіть свою адресу у графіку відключень:", reply_markup=unknown_keyboard("back_to_start"))
    elif text == "ℹ️ Про бота":
        await update.message.reply_text(
            "ℹ️ Бот допомагає відстежувати графіки відключень електропостачання у Черкаській області.\n\nНе є офіційним джерелом інформації",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💖 Підтримати проєкт", callback_data="support_project_from_about")]]),
        )

async def back_to_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "ℹ️ Бот допомагає відстежувати графік відключень у Черкаській області.\n\nНе є офіційним джерелом інформації",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💖 Підтримати проєкт", callback_data="support_project_from_about")]
        ]),
    )

# === Оновлена клавіатура PDF ===
def pdf_download_keyboard(back_cb: str):
    rows = []
    for i in range(1, 7):
        for j in (1, 2):
            emoji = QUEUE_EMOJI[i - 1]
            label = f"{emoji} черга {'Ⅰ' if j == 1 else 'Ⅱ'} підчерга"
            callback = f"download_pdf_{i}{j}"
            rows.append([InlineKeyboardButton(label, callback_data=callback)])
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=back_cb)])
    return InlineKeyboardMarkup(rows)

# === Показ списку PDF ===
async def show_pdfs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📄 Виберіть графік черги для завантаження:",
        reply_markup=pdf_download_keyboard("unknown_queue")
    )

# === Завантаження PDF-файлу з URL і надсилання користувачу ===
async def download_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pdf_id = query.data.replace("download_pdf_", "")
    pdf_url = f"https://storage.googleapis.com/ck_blackout_pdf/Графік_черга_{pdf_id}.pdf"
    file_name = f"Графік_{pdf_id}.pdf"

    # Повідомлення про завантаження
    loading_msg = await query.message.reply_text("⏳ Завантажуємо файл...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(pdf_url) as resp:
                if resp.status == 200:
                    # Файл існує → Telegram сам завантажить його напряму
                    await query.message.reply_document(document=pdf_url, filename=file_name)
                elif resp.status == 404:
                    await query.message.reply_text("❌ Файл не знайдено. Можливо, ще не оновили графік.")
                else:
                    await query.message.reply_text(f"⚠️ Помилка доступу до файлу (код {resp.status}).")
    except Exception as e:
        await query.message.reply_text(f"⚠️ Помилка при перевірці файлу: {e}")

    # Видаляємо повідомлення про завантаження
    await loading_msg.delete()

# === Реєстрація в main() ===



# === Main ===
async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не задано. Додайте його в .env або змінні середовища.")
        return

    await init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", show_main_menu))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_command))
    app.add_handler(CallbackQueryHandler(queue_choice, pattern="^queue_"))
    app.add_handler(CallbackQueryHandler(sub_choice, pattern="^sub_"))
    app.add_handler(CallbackQueryHandler(lambda u, c: support_project(u, c, "back_to_support_prev"), pattern="^support_project_from_sub$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: support_project(u, c, "back_to_about"), pattern="^support_project_from_about$"))
    app.add_handler(CallbackQueryHandler(donate_choice, pattern="^donate_"))
    app.add_handler(CallbackQueryHandler(unknown_queue, pattern="^unknown_queue$"))
    app.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))
    app.add_handler(CallbackQueryHandler(back_to_queue, pattern="^back_to_queue_"))
    app.add_handler(CallbackQueryHandler(back_to_support_prev, pattern="^back_to_support_prev$"))
    app.add_handler(CallbackQueryHandler(back_to_about, pattern="^back_to_about$"))
    app.add_handler(CallbackQueryHandler(show_main_menu, pattern="^main_menu$"))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    app.add_handler(CallbackQueryHandler(show_pdfs, pattern="^show_pdfs$"))
    
    app.add_handler(CallbackQueryHandler(download_pdf, pattern="^download_pdf_"))

    logger.info("Бот запущено з уточненим діалогом підтримки")
    await app.run_polling()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())
