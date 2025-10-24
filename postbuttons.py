import asyncio
import os
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder

# === Завантаження токена з .env ===
load_dotenv()
BOT_TOKEN = os.getenv("TEST_BOT_TOKEN")

# === Канал або чат ===
CHAT_ID = "-1002930307928"   # 🔹 заміни на свій канал або чат

# === Текст повідомлення ===
MESSAGE_TEXT = (
    "💡 Всі черги відключень у Черкаській області:\n"
    "👇 Посилання на канали"
)

# === Inline-кнопки для черг і підчерг ===
keyboard = [
    [
        InlineKeyboardButton("🔴 Черга 1.1", url="https://t.me/ck_blackout_1_1"),
        InlineKeyboardButton("🔴 Черга 1.2", url="https://t.me/ck_blackout_1_2"),
    ],
    [
        InlineKeyboardButton("🟠 Черга 2.1", url="https://t.me/ck_blackout_2_1"),
        InlineKeyboardButton("🟠 Черга 2.2", url="https://t.me/ck_blackout_2_2"),
    ],
    [
        InlineKeyboardButton("🟢 Черга 3.1", url="https://t.me/ck_blackout_3_1"),
        InlineKeyboardButton("🟢 Черга 3.2", url="https://t.me/ck_blackout_3_2"),
    ],
    [
        InlineKeyboardButton("🔵 Черга 4.1", url="https://t.me/ck_blackout_4_1"),
        InlineKeyboardButton("🔵 Черга 4.2", url="https://t.me/ck_blackout_4_2"),
    ],
    [
        InlineKeyboardButton("🟣 Черга 5.1", url="https://t.me/ck_blackout_5_1"),
        InlineKeyboardButton("🟣 Черга 5.2", url="https://t.me/ck_blackout_5_2"),
    ],
    [
        InlineKeyboardButton("🟡 Черга 6.1", url="https://t.me/ck_blackout_6_1"),
        InlineKeyboardButton("🟡 Черга 6.2", url="https://t.me/ck_blackout_6_2"),
    ],
    [
        InlineKeyboardButton("🔔 Сповіщення бот", url="https://t.me/ck_blackout_bot"),
    ],
]

reply_markup = InlineKeyboardMarkup(keyboard)

# === Відправлення повідомлення ===
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    await app.bot.send_message(
        chat_id=CHAT_ID,
        text=MESSAGE_TEXT,
        parse_mode="HTML",
        reply_markup=reply_markup,
        disable_notification=True
    )
    print("✅ Повідомлення з кнопками успішно надіслано!")

if __name__ == "__main__":
    asyncio.run(main())
