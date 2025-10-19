import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    PreCheckoutQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Налаштування логування
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота від @BotFather
BOT_TOKEN = "8360852576:AAFRR2sbMqN5_2MriZRnSjboDigXxlTFijM"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Вітаю! Використовуйте /buy для покупки за Stars.")

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Купити за 10 Stars", callback_data="buy_item")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Купіть цифровий товар за 10 Telegram Stars!", reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "buy_item":
        # Ціна в Stars (LabeledPrice для Bot API v6+)
        prices = [LabeledPrice("Цифровий товар", 10)]  # 10 Stars
        await context.bot.send_invoice(
            chat_id=query.message.chat_id,
            title="Цифровий товар",
            description="Приклад: доступ до контенту",
            payload="item_001",
            currency="XTR",  # Telegram Stars
            prices=prices,
            provider_token="",  # Порожній для Stars
            start_parameter="buy-item",
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
        )

async def pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    if query.invoice_payload != "item_001":
        await query.answer(ok=False, error_message="Невірний товар")
    else:
        await query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    await update.message.reply_text(f"Дякуємо! Оплатили {payment.total_amount} Stars. Ось ваш товар: [посилання або файл].")

async def paysupport(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Зверніться до підтримки: @your_support_bot. Обробимо запит за 24 год.")

async def terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Умови: Покупець погоджується з поверненням Stars за запитом. Деталі: [текст].")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("paysupport", paysupport))
    app.add_handler(CommandHandler("terms", terms))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout_query))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    app.run_polling()

if __name__ == "__main__":
    main()