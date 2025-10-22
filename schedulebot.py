import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, time
from pathlib import Path

import pytz
from dotenv import load_dotenv
from telegram import Bot
from telegram.constants import ParseMode

# ================== INIT ==================
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SCHEDULE_FILE = Path(os.getenv("SCHEDULE_FILE", "schedule.json"))
STATE_FILE = Path("bot_state.json")
TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Europe/Kyiv"))

bot = Bot(token=BOT_TOKEN)

# Track schedule file mtime & tasks
last_schedule_mtime: float | None = None
current_schedule: dict = {}
scheduled_tasks: list[asyncio.Task] = []

# ================== STATE ==================
def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def cleanup_state(state, days: int = 10):
    cutoff = datetime.now() - timedelta(days=days)
    new_state = {}
    for key, value in state.items():
        try:
            dt = datetime.strptime(key.split("_")[-1], "%Y-%m-%d_%H:%M")
            if dt > cutoff:
                new_state[key] = value
        except Exception:
            new_state[key] = value
    if len(new_state) != len(state):
        save_state(new_state)
        logging.info("🧹 Очищено старі записи зі стану (старше %d діб)", days)
    return new_state


bot_state = cleanup_state(load_state())

# ================== HELPERS ==================
def local_now() -> datetime:
    return datetime.now(TIMEZONE)


def today_timestr_to_datetime(timestr: str) -> datetime:
    now = local_now()
    hour, minute = map(int, timestr.split(":"))
    return TIMEZONE.localize(datetime.combine(now.date(), time(hour, minute)))


def load_schedule() -> tuple[dict, bool]:
    """Return (schedule, changed_flag)."""
    global last_schedule_mtime, current_schedule
    if not SCHEDULE_FILE.exists():
        logging.warning("⚠️ Файл розкладу не знайдено!")
        return {}, False

    mtime = SCHEDULE_FILE.stat().st_mtime
    changed = last_schedule_mtime is None or mtime != last_schedule_mtime
    if changed:
        last_schedule_mtime = mtime
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            current_schedule = json.load(f)
        logging.info("🔁 Розклад оновлено з файлу.")
    return current_schedule, changed


def schedule_task(coro: asyncio.coroutines):
    task = asyncio.create_task(coro)
    scheduled_tasks.append(task)
    return task


def cancel_all_scheduled_tasks():
    """Cancel pending scheduled tasks when the schedule changes."""
    alive = 0
    for t in scheduled_tasks:
        if not t.done():
            t.cancel()
            alive += 1
    scheduled_tasks.clear()
    if alive:
        logging.info("🛑 Скасовано %d попередніх задач(і) планувальника.", alive)


# ================== SCHEDULER ==================
async def schedule_daily_tasks():
    schedule, _ = load_schedule()
    now = local_now()
    logging.info("📅 Планування постів на поточну добу...")

    for friendly_name, data in schedule.items():
        channel = data["channel_id"]
        periods = data["periods"]

        for i, (start_str, end_str) in enumerate(periods):
            start_dt = today_timestr_to_datetime(start_str)
            end_dt = today_timestr_to_datetime(end_str)

            # Перехід через північ
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)

            # Якщо період уже минув повністю — перенесемо на наступну добу
            if end_dt < now:
                start_dt += timedelta(days=1)
                end_dt += timedelta(days=1)

            # ВИМКНЕННЯ
            schedule_task(
                maybe_post_message(
                    channel,
                    friendly_name,
                    (
                        f"⚡ Черга {friendly_name}\n"
                        f"🔴 ВИМКНЕННЯ з {start_dt.strftime('%H:%M')} до {end_dt.strftime('%H:%M')}\n"
                        f"💡 Увімкнення о {end_dt.strftime('%H:%M')}"
                    ),
                    start_dt,
                    "off",
                )
            )

            # УВІМКНЕННЯ
            next_off = periods[i + 1][0] if i + 1 < len(periods) else None
            next_text = f"⚡ Черга {friendly_name}\n🟢 СВІТЛО УВІМКНЕНО о {end_dt.strftime('%H:%M')}"
            if next_off:
                next_text += f"\n🔴 Наступне вимкнення о {next_off}"

            schedule_task(maybe_post_message(channel, friendly_name, next_text, end_dt, "on"))

    logging.info("✅ Нові задачі створено.")


async def maybe_post_message(channel_id, friendly_name, text, send_time, event_type):
    # Очікування до часу публікації
    delay = (send_time - local_now()).total_seconds()
    if delay > 0:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return

    key = f"{friendly_name}_{event_type}_{send_time.strftime('%Y-%m-%d_%H:%M')}"
    if bot_state.get(key):
        logging.info("⏩ Пропущено дубльоване повідомлення: %s", key)
        return

    await post_message(channel_id, text)
    bot_state[key] = True
    save_state(bot_state)


async def post_message(channel_id, text):
    try:
        await bot.send_message(chat_id=channel_id, text=text, parse_mode=ParseMode.HTML)
        logging.info("📤 Повідомлення надіслано у %s", channel_id)
    except Exception as e:
        logging.error("❌ Помилка при відправленні у %s: %s", channel_id, e)


# ================== MAIN ==================
async def main():
    logging.info("🚀 Бот запущено.")

    # Початкове планування
    await schedule_daily_tasks()

    # Наступна північ для щоденного перепланування
    def next_midnight(dt: datetime) -> datetime:
        return (dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    rollover_at = next_midnight(local_now())

    while True:
        # Перевіряти файл розкладу щохвилини
        await asyncio.sleep(60)
        _, changed = load_schedule()
        now = local_now()

        # Перепланування при зміні розкладу
        if changed:
            cancel_all_scheduled_tasks()
            await schedule_daily_tasks()
            # оновити північ, на випадок редагування близько до опівночі
            rollover_at = next_midnight(now)
            continue

        # Перепланування на нову добу
        if now >= rollover_at:
            cancel_all_scheduled_tasks()
            await schedule_daily_tasks()
            rollover_at = next_midnight(now)


if __name__ == "__main__":
    asyncio.run(main())
