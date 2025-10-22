import logging
import sqlite3
import os
from dotenv import load_dotenv
from datetime import datetime
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# === .env ===
load_dotenv()

# === Config ===
BOT_TOKEN = os.getenv("BOT_START_TOKEN")

# --- створення БД користувачів ---
conn = sqlite3.connect("users.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    start_time TEXT,
    is_premium INTEGER DEFAULT 0
)
""")
conn.commit()

# --- посилання на групи ---
GROUP_LINKS = {
    "1_1": "https://t.me/ck_blackout_1_1",
    "1_2": "https://t.me/ck_blackout_1_2",
    "2_1": "https://t.me/ck_blackout_2_1",
    "2_2": "https://t.me/ck_blackout_2_2",
    "3_1": "https://t.me/ck_blackout_3_1",
    "3_2": "https://t.me/ck_blackout_3_2",
    "4_1": "https://t.me/ck_blackout_4_1",
    "4_2": "https://t.me/ck_blackout_4_2",
    "5_1": "https://t.me/ck_blackout_5_1",
    "5_2": "https://t.me/ck_blackout_5_2",
    "6_1": "https://t.me/ck_blackout_6_1",
    "6_2": "https://t.me/ck_blackout_6_2",
}

# --- emoji для черг ---
QUEUE_EMOJI = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]

# --- логування ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

miniapp_url = "https://cherkasyoblenergo.com/static/perelik-gpv"#https://wgis.project.co.ua/pano
# === Утиліти для клавіатур (чітко формують рядки) ===

def build_start_keyboard():
    # одна кнопка на рядок з підписами
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{QUEUE_EMOJI[0]} Черга", callback_data="queue_1")],
        [InlineKeyboardButton(f"{QUEUE_EMOJI[1]} Черга", callback_data="queue_2")],
        [InlineKeyboardButton(f"{QUEUE_EMOJI[2]} Черга", callback_data="queue_3")],
        [InlineKeyboardButton(f"{QUEUE_EMOJI[3]} Черга", callback_data="queue_4")],
        [InlineKeyboardButton(f"{QUEUE_EMOJI[4]} Черга", callback_data="queue_5")],
        [InlineKeyboardButton(f"{QUEUE_EMOJI[5]} Черга", callback_data="queue_6")],
        [InlineKeyboardButton(f"🤷‍♂️ Я не знаю", callback_data="unknown_queue")]
    ])


def build_subkeyboard(queue: int):
    # підчерги і назад
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Ⅰ підчерга", callback_data=f"sub_{queue}_1"), InlineKeyboardButton("Ⅱ підчерга", callback_data=f"sub_{queue}_2")],
        [InlineKeyboardButton(f"🤷‍♂️ Я не знаю", callback_data="unknown_queue")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_start")]
    ])


def build_subscription_options(key: str):
    # key як "3_2"
    group_url = GROUP_LINKS.get(key, "#")
    queue, sub = key.split("_")
    queue_label = f"{QUEUE_EMOJI[int(queue)-1]} черга {'Ⅰ' if sub=='1' else 'Ⅱ'} підчерга"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Отримувати сповіщення в каналі", url=group_url)],
        [InlineKeyboardButton("💫 Отримувати сповіщення в боті", callback_data=f"personal_{key}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_queue_{queue}")]
    ])

async def subscription_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    # Очікуємо кнопку для персональних сповіщень
    if data.startswith("personal_"):
        key = data.split("personal_")[1]
        queue, sub = key.split("_")
        queue_label = f"{QUEUE_EMOJI[int(queue)-1]} черга {'Ⅰ' if sub=='1' else 'Ⅱ'} підчерга"
        group_url = GROUP_LINKS.get(key, '#')

        # Виклик функції для виведення повідомлення з кнопками Оплатити / Безкоштовно
        await send_personal_alert_options(chat_id=query.from_user.id, context=context, queue_label=queue_label, group_url=group_url, key=key)

# === ОБРОБНИКИ ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cur.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, start_time) VALUES (?, ?, ?, ?)",
        (user.id, user.username, user.first_name, datetime.now().isoformat())
    )
    conn.commit()

    await update.message.reply_text(
        f"👋 Вітаю, {user.first_name or 'друже'}!\n\n"
        "💡 Щоб отримувати сповіщення потрібно обрати чергу і підчергу погодинних відключень:\n\n"
    )

    text = (
        "Спочатку оберіть свою чергу у графіку відключень:\n"
        "⬇️⬇️⬇️"
    )
    await update.message.reply_text(text, reply_markup=build_start_keyboard())


async def queue_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Захищений парсинг: очікуємо формат queue_N
    data = query.data
    if not data.startswith("queue_"):
        # не наше, ігноруємо
        return

    raw = data.split("_")[1]
    if not raw.isdigit():
        return
    queue = int(raw)

    text = (
        f"📊 Ви обрали <b>{QUEUE_EMOJI[queue-1]} чергу</b>.\n\n"
        "Тепер виберіть свою підчергу:"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=build_subkeyboard(queue))


async def subqueue_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    # очікуємо формат sub_N_M
    if not data.startswith("sub_"):
        return
    parts = data.split("_")
    if len(parts) != 3:
        return
    _, q_str, sub_str = parts
    if not q_str.isdigit() or not sub_str.isdigit():
        return
    queue = int(q_str)
    sub = int(sub_str)
    queue_label = f"{QUEUE_EMOJI[int(queue)-1]} черга {'Ⅰ' if sub=='1' else 'Ⅱ'} підчерга"
    key = f"{queue}_{sub}"
    text = (
        f"🔌 Ви обрали <b>{QUEUE_EMOJI[queue-1]} чергу</b>, {'Ⅰ' if sub==1 else 'Ⅱ'} підчергу.\n\n"
        f"• 💬 Приєднайтесь до каналу Графік відключень {queue_label} та отримуйте сповіщення про відключення електроенергії.\n\n"
        "або\n\n"
        "• 💫 Отримуйте персоналізовані сповіщення в боті"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=build_subscription_options(key))
    

async def back_to_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # pattern back_to_queue_N
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split("_")
    if len(parts) < 4:
        # fallback to start
        await query.edit_message_text("Оберіть чергу:", reply_markup=build_start_keyboard())
        return
    queue = parts[-1]
    if not queue.isdigit():
        await query.edit_message_text("Оберіть чергу:", reply_markup=build_start_keyboard())
        return
    # показати підчерги для цього queue
    await query.edit_message_text(
        f"📊 Ви обрали <b>{QUEUE_EMOJI[int(queue)-1]} чергу</b>.\n\nТепер виберіть свою підчергу:",
        parse_mode="HTML",
        reply_markup=build_subkeyboard(int(queue))
    )


async def back_to_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    text = (
        "Оберіть свою чергу графіку відключень:\n"
        "⬇️⬇️⬇️"
    )
    await query.edit_message_text(text, reply_markup=build_start_keyboard())

async def send_personal_alert_options(chat_id, context: ContextTypes.DEFAULT_TYPE, queue_label, group_url, key):
    """
    Надсилає повідомлення про переваги персоналізованих сповіщень
    з двома кнопками: Оплатити 10 Stars та Отримувати безкоштовно
    """


    description = (
    f"  ✨ Переваги персональних сповіщень в боті:\n\n"
            f"⏱️ Налаштування сповіщень за 5/10/15 або 20 хвилин до відключення\n"
            f"💬 Сповіщення про декілька черг в одному чаті\n"             
            f"🌙 Вимкнення сповіщень у нічний час\n"
            f"🔕 Без спаму, лише корисна інформація\n"
            f"🙏 Ви підтримуєте цей проєкт. (одноразовий платіж 10 ⭐️ ≈10₴)\n\n"
            f"або\n\n"
            f"• 💬 Приєднайтесь до каналу «Графік відключень {queue_label}» та отримуйте сповіщення про відключення електроенергії безкоштовно.\n\n"

    )


    keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("Сповіщення в боті за 10 ⭐️", callback_data=f"buy_{key}")],
    [InlineKeyboardButton(f"💬 Отримувати сповіщення в каналі", url=group_url)]
    ])


    await context.bot.send_message(chat_id=chat_id, text=description, reply_markup=keyboard)
# === Оплата Telegram Stars ===
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    if data.startswith("buy_"):
        key = data.split("_", 1)[1]
        q_part, s_part = key.split("_")
        queue = int(q_part)
        sub = int(s_part)
        queue_label = f"{QUEUE_EMOJI[queue-1]} черга {'Ⅰ' if sub == 1 else 'Ⅱ'} підчерга"

        description = (
            f"✨ Отримуєте всі переваги персональних сповіщень в боті\n\n"
            f"та підтримуєте цей проєкт. Дякуємо!\n"
            f"Вартість: 10⭐️"
        )

        prices = [LabeledPrice("Персоналізовані сповіщення", 10)]  # 10 Stars
        await context.bot.send_invoice(
            chat_id=query.from_user.id,
            title="⭐️ Персоналізовані сповіщення",
            description=description,
            payload=f"stars_{key}",
            currency="XTR",
            prices=prices,
            provider_token="",  # порожній для Telegram Stars
            start_parameter="personal_alerts"
        )

        extra_button = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"💬 Отримувати сповіщення в каналі {queue_label}", url=GROUP_LINKS[key])],
            [InlineKeyboardButton("⬅️ Повернутися до вибору черги", callback_data="start_over")]
        ])

        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=f"Або приєднайтесь до каналу {queue_label} та отримуйте сповіщення про відключення електроенергії безкоштовно",
            reply_markup=extra_button
        )
async def start_over_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Використовуємо edit_message_text, щоб оновити поточне повідомлення, якщо update.callback_query
    if query.message:
        await query.edit_message_text(
            f"👋 Вітаю, {query.from_user.first_name or 'друже'}!\n\nОберіть свою чергу графіку відключень:\n⬇️⬇️⬇️",
            reply_markup=build_start_keyboard()
        )
    else:
        await start(update, context)

async def unknown_queue_callback(update, context):
    query = update.callback_query
    await query.answer()

    miniapp_url = "https://cherkasyoblenergo.com/static/perelik-gpv"  # https://wgis.project.co.ua/pano заміни на свій URL Mini App

    miniapp_button = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Відкрити Пошук", web_app={"url": miniapp_url})],
        [InlineKeyboardButton("⬅️ Назад", callback_data="delete_and_back")]
    ])

    await query.message.reply_text(
        "Якщо не знаєте свою чергу — скористайтеся пошуком:",
        reply_markup=miniapp_button
    )


async def pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if not query.invoice_payload.startswith("stars_"):
        await query.answer(ok=False, error_message="Помилка під час оплати.")
    else:
        await query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    key = payment.invoice_payload.replace("stars_", "")
    user_id = update.effective_user.id

    cur.execute("UPDATE users SET is_premium = 1 WHERE user_id = ?", (user_id,))
    conn.commit()

    await update.message.reply_text(
        f"✅ Дякуємо за оплату 10⭐️!\n\n"
        f"Персоналізовані сповіщення для <b>{key}</b> активовано 🔔",
        parse_mode="HTML"
    )

async def delete_and_back_callback(update, context):
    query = update.callback_query
    await query.answer()

    try:
        await query.message.delete()
    except Exception as e:
        print(f"Не вдалося видалити повідомлення: {e}")

# === ЗАПУСК ===
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(queue_choice, pattern="^queue_"))
    app.add_handler(CallbackQueryHandler(subqueue_choice, pattern="^sub_"))
    app.add_handler(CallbackQueryHandler(back_to_queue, pattern="^back_to_queue_"))
    app.add_handler(CallbackQueryHandler(back_to_start_handler, pattern="^back_to_start$"))
    app.add_handler(CallbackQueryHandler(start_over_callback, pattern="^start_over$"))
    app.add_handler(CallbackQueryHandler(button_callback, pattern="^buy_"))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_query))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.add_handler(CallbackQueryHandler(subscription_choice_callback, pattern="^personal_"))
    app.add_handler(CallbackQueryHandler(unknown_queue_callback, pattern="^unknown_queue$"))
    app.add_handler(CallbackQueryHandler(delete_and_back_callback, pattern="^delete_and_back$"))


    app.run_polling()


if __name__ == "__main__":
    main()
