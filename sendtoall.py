import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
import os
from dotenv import load_dotenv
load_dotenv()

# === Config ===
BOT_TOKEN = "8291315042:AAHKAMx0TLQZslE8301MfhFaAgAVCnjSVvo"  # 🔹 встав свій токен
ALLOWED_USERS = {1287504040, 348150320}  # 🔹 ID користувачів, яким дозволено надсилати
CHANNELS = [
    "-1003113234171","-1003145633887","-1003138079087","-1003128920788","-1002967860214","-1003033893922","-1003009930050","-1003170499896","-1003096266337","-1003169834725","-1002988126895"
]

# ==== ЛОГІНГ ====
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)


# ==== ГОЛОВНА ФУНКЦІЯ ====
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    caption = update.message.caption or ""
    photo = update.message.photo[-1]  # найбільше фото

    # Перевірка доступу
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text("⛔ Вам заборонено користуватися цією функцією.")
        log.warning(f"Заборонена спроба від {user_name} ({user_id})")
        return

    file_id = photo.file_id
    success, fail = 0, 0

    for channel in CHANNELS:
        try:
            # Надсилаємо фото з підписом
            msg = await context.bot.send_photo(chat_id=channel, photo=file_id, caption=caption)
            # Закріплюємо повідомлення
            await context.bot.pin_chat_message(chat_id=channel, message_id=msg.message_id, disable_notification=False)

            success += 1
            log.info(f"✅ Відправлено і закріплено в {channel}")

        except Exception as e:
            fail += 1
            log.error(f"❌ Помилка для {channel}: {e}")

    await update.message.reply_text(f"✅ Успішно: {success}\n❌ Помилки: {fail}")



# ==== СТАРТ ====
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Обробляємо лише фото з підписом (або без)
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("🚀 Бот запущений. Очікує зображення...")
    app.run_polling()
