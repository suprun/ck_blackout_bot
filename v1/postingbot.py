import os
import threading
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
)

from schedule_manager import ScheduleManager

# watchdog для автооновлення JSON
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# === Конфіг ===
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
CHANNEL_IDS = [int(x.strip()) for x in os.getenv("CHANNEL_IDS", "").split(",") if x.strip()]
TZ = os.getenv("TZ", "Europe/Kyiv")

# === Ініціалізація бота ===
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Базові інтервали для старту (щоб було що зберегти у schedule.json, якщо він порожній)
DEFAULT_SCHEDULE = {
    ch: [
        {"on": datetime.strptime("06:00", "%H:%M").time(), "off": datetime.strptime("08:00", "%H:%M").time()},
        {"on": datetime.strptime("12:00", "%H:%M").time(), "off": datetime.strptime("14:00", "%H:%M").time()},
        {"on": datetime.strptime("18:00", "%H:%M").time(), "off": datetime.strptime("20:00", "%H:%M").time()},
    ]
    for ch in CHANNEL_IDS
}

scheduler = ScheduleManager(app.bot, DEFAULT_SCHEDULE, timezone=TZ)
# якщо є файли — завантажимо
'''scheduler.load_schedule()
scheduler.start()'''

# === Доступ ===
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# === Команди (усі тільки для адмінів) ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Цей бот не доступний для публічного використання.")
    await update.message.reply_text("🤖 Бот активний. Використайте /help або /menu.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу.")
    await update.message.reply_text(
        "📋 Команди адміністратора:\n"
        "/menu — відкрити адмін-меню\n"
        "/broadcast <текст> — розсилка у всі канали\n"
        "/update_schedule <idx> <on_HH:MM> <off_HH:MM> — додати інтервал\n"
        "/showschedule — показати ON/OFF\n"
        "/showschedule_info — показати інфо-повідомлення\n"
        "/update_info <HH:MM> text <текст> — додати інфо-текст\n"
        "/update_info <HH:MM> photo — надішліть із фото та підписом\n"
        "/clear_info <номер|all> — видалити інфо\n"
        "/pause — пауза для всіх\n"
        "/resume — відновити всі\n"
        "/pause_channel <idx> — пауза для каналу\n"
        "/resume_channel <idx> — відновити канал\n"
        "/history — показати останні 10 записів\n"
        "/reload — перечитати JSON (schedule/info)"
    )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу.")
    if not context.args:
        return await update.message.reply_text("Вкажіть текст після /broadcast")
    text = " ".join(context.args)
    for ch in CHANNEL_IDS:
        try:
            await context.bot.send_message(ch, text)
            scheduler.add_to_history(ch, "broadcast", text)
        except Exception as e:
            print(f"Помилка надсилання у {ch}: {e}")
    await update.message.reply_text("✅ Розсилку виконано.")

async def send_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # фото + підпис -> розсилка
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу.")
    caption = update.message.caption or ""
    photo = update.message.photo[-1].file_id
    for ch in CHANNEL_IDS:
        try:
            await context.bot.send_photo(ch, photo=photo, caption=caption)
            scheduler.add_to_history(ch, "broadcast_photo", caption)
        except Exception as e:
            print(f"Помилка у {ch}: {e}")
    await update.message.reply_text("🖼 Фото розіслано у всі канали.")

async def update_schedule_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу.")
    if len(context.args) < 3:
        return await update.message.reply_text("Формат: /update_schedule <індекс> <on_HH:MM> <off_HH:MM>")
    try:
        idx = int(context.args[0])
        on_t = datetime.strptime(context.args[1], "%H:%M").time()
        off_t = datetime.strptime(context.args[2], "%H:%M").time()
        ch_id = CHANNEL_IDS[idx]
        scheduler.channels.setdefault(ch_id, []).append({"on": on_t, "off": off_t})
        scheduler.update_schedule(scheduler.channels)
        await update.message.reply_text(f"✅ Додано інтервал для каналу #{idx}")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}")

async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу.")
    text = "📅 Поточний графік:\n\n"
    for i, (ch, intervals) in enumerate(scheduler.channels.items()):
        text += f"#{i} — {ch}\n"
        for j, t in enumerate(intervals, 1):
            text += f"  • {j}: ON {t['on'].strftime('%H:%M')} | OFF {t['off'].strftime('%H:%M')}\n"
    await update.message.reply_text(text)

async def update_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу.")
    # текстовий варіант
    if len(context.args) >= 2 and not update.message.photo:
        time_str = context.args[0]
        msg_type = context.args[1].lower()
        if msg_type != "text":
            return await update.message.reply_text("Формат: /update_info <HH:MM> text <текст>")
        text = " ".join(context.args[2:])
        scheduler.add_info_message(time_str, "text", text=text)
        return await update.message.reply_text(f"✅ Додано інфо-текст на {time_str}")
    # фото-варіант
    if update.message.photo:
        if len(context.args) < 1:
            return await update.message.reply_text("Формат: /update_info <HH:MM> photo (надішліть із фото)")
        time_str = context.args[0]
        photo_id = update.message.photo[-1].file_id
        caption = update.message.caption or ""
        scheduler.add_info_message(time_str, "photo", photo=photo_id, caption=caption)
        return await update.message.reply_text(f"🖼 Додано інфо-фото на {time_str}")
    await update.message.reply_text(
        "❌ Приклади:\n"
        "/update_info 10:00 text ⚡ Повідомлення\n"
        "або надішліть фото + /update_info 12:00 photo"
    )

async def show_info_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу.")
    info = scheduler.info_schedule
    if not info:
        return await update.message.reply_text("ℹ️ Розклад інформаційних повідомлень порожній.")
    txt = "🗓️ Розклад інформаційних повідомлень:\n\n"
    for i, m in enumerate(info, 1):
        kind = "📝 Текст" if m["type"] == "text" else "🖼 Фото"
        preview = m.get("text") or m.get("caption") or ""
        if len(preview) > 100:
            preview = preview[:100] + "..."
        txt += f"{i}. ⏰ {m['time']} | {kind}\n   {preview}\n\n"
    await update.message.reply_text(txt)

async def clear_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу.")
    if not context.args:
        return await update.message.reply_text("Формат: /clear_info <номер> або /clear_info all")
    arg = context.args[0].lower()
    info = scheduler.info_schedule
    if not info:
        return await update.message.reply_text("ℹ️ Розклад порожній.")
    try:
        if arg == "all":
            scheduler.info_schedule = []
            scheduler.save_info_schedule()
            scheduler._schedule_all()
            return await update.message.reply_text("🗑 Усі інформаційні повідомлення видалено.")
        idx = int(arg) - 1
        if idx < 0 or idx >= len(info):
            return await update.message.reply_text("⚠️ Неправильний номер.")
        removed = info.pop(idx)
        scheduler.save_info_schedule()
        scheduler._schedule_all()
        pv = removed.get("text") or removed.get("caption") or ""
        if len(pv) > 100:
            pv = pv[:100] + "..."
        await update.message.reply_text(f"🗑 Видалено #{arg} ({removed['time']}): {pv}")
        await show_info_schedule(update, context)
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}")

async def pause_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу.")
    scheduler.pause_notifications()
    await update.message.reply_text("⏸ Сповіщення призупинено для всіх каналів.")

async def resume_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу.")
    scheduler.resume_notifications()
    scheduler.paused_channels.clear()
    await update.message.reply_text("▶️ Сповіщення відновлено для всіх каналів.")

async def pause_channel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу.")
    if len(context.args) < 1:
        return await update.message.reply_text("Формат: /pause_channel <індекс>")
    try:
        idx = int(context.args[0])
        ch_id = CHANNEL_IDS[idx]
        scheduler.pause_channel(ch_id)
        await update.message.reply_text(f"⏸ Канал #{idx} ({ch_id}) призупинено.")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}")

async def resume_channel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу.")
    if len(context.args) < 1:
        return await update.message.reply_text("Формат: /resume_channel <індекс>")
    try:
        idx = int(context.args[0])
        ch_id = CHANNEL_IDS[idx]
        scheduler.resume_channel(ch_id)
        await update.message.reply_text(f"▶️ Канал #{idx} ({ch_id}) відновлено.")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка: {e}")

async def show_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу.")
    entries = scheduler.history[-10:]
    if not entries:
        return await update.message.reply_text("Історія порожня.")
    txt = "🕓 Останні повідомлення:\n\n"
    for e in entries:
        txt += f"[{e['time']}] {e['type'].upper()} — {e['channel']}: {e['text']}\n"
    await update.message.reply_text(txt)

async def reload_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return await update.message.reply_text("⛔ Немає доступу.")
    try:
        scheduler.clear_jobs()
        scheduler.load_schedule()                 # schedule.json
        scheduler.info_schedule = scheduler._load_info_schedule()  # info_schedule.json
        scheduler._schedule_all()
        scheduler.touch_reload_timestamp()
        await update.message.reply_text("🔄 Графіки успішно оновлено з JSON файлів.")
        print("✅ Перечитано графіки вручну (/reload)")
    except Exception as e:
        await update.message.reply_text(f"❌ Помилка оновлення: {e}")

# === Watchdog автооновлення ===
class FileWatcher(FileSystemEventHandler):
    def __init__(self, scheduler: ScheduleManager):
        self.scheduler = scheduler

    def on_modified(self, event):
        if event.src_path.endswith("schedule.json") or event.src_path.endswith("info_schedule.json"):
            print(f"📁 Змінено файл: {event.src_path}. Перечитую графіки...")
            try:
                self.scheduler.clear_jobs()
                self.scheduler.load_schedule()
                self.scheduler.info_schedule = self.scheduler._load_info_schedule()
                self.scheduler._schedule_all()
                self.scheduler.touch_reload_timestamp()
                print("✅ Автоматично оновлено розклад")
            except Exception as e:
                print(f"❌ Помилка автооновлення: {e}")

def start_file_watcher(scheduler: ScheduleManager):
    observer = Observer()
    observer.schedule(FileWatcher(scheduler), ".", recursive=False)
    observer.start()
    threading.Thread(target=observer.join, daemon=True).start()

# === Реєстрація хендлерів ===
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help_command))
app.add_handler(CommandHandler("menu", lambda u, c: None))  # заповнить admin_menu
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CommandHandler("update_schedule", update_schedule_cmd))
app.add_handler(CommandHandler("showschedule", show_schedule))
app.add_handler(CommandHandler("showschedule_info", show_info_schedule))
app.add_handler(CommandHandler("update_info", update_info))
app.add_handler(CommandHandler("clear_info", clear_info))
app.add_handler(CommandHandler("pause", pause_notifications))
app.add_handler(CommandHandler("resume", resume_notifications))
app.add_handler(CommandHandler("pause_channel", pause_channel_cmd))
app.add_handler(CommandHandler("resume_channel", resume_channel_cmd))
app.add_handler(CommandHandler("history", show_history))
app.add_handler(CommandHandler("reload", reload_schedules))
# фото як розсилка
app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, send_image))

# === Підключення розширеного адмін-меню ===
from admin_menu import register_admin_menu
register_admin_menu(app)

import asyncio

async def main():
    # Завантажуємо розклади
    scheduler.load_schedule()
    # Стартуємо після створення подійного циклу
    scheduler.start()
    print("🤖 Бот запущено")
    start_file_watcher(scheduler)
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
