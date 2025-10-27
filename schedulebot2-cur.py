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
SCHEDULE_TOMORROW_FILE = Path(os.getenv("SCHEDULE_TOMORROW_FILE", "schedule_tomorrow.json"))
STATE_FILE = Path("bot_state.json")
MAX_STATE_ENTRIES = 1000
TIMEZONE = pytz.timezone(os.getenv("TIMEZONE", "Europe/Kyiv"))

POST_LINKS_FILE = Path("post_links_today.json")
POST_LINKS_TOMORROW_FILE = Path("post_links_tomorrow.json")

bot = Bot(token=BOT_TOKEN)

last_schedule_mtime = None
last_schedule_tomorrow_mtime = None
current_schedule = {}
current_schedule_tomorrow = {}
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
    # Якщо перевищено межу — видаляємо найстаріші ключі
    if len(state) > MAX_STATE_ENTRIES:
        oldest_keys = sorted(state.keys())[:len(state) - MAX_STATE_ENTRIES]
        for k in oldest_keys:
            del state[k]
        logging.info(f"⚠️ Скорочено bot_state.json до {MAX_STATE_ENTRIES} записів.")
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


def day_timestr_to_datetime(timestr: str, day_offset: int = 0, is_end: bool = False) -> datetime:
    """Конвертує рядок 'HH:MM' у datetime з урахуванням часового поясу.
       Якщо це кінець періоду (is_end=True) і час 00:00, вважається наступним днем.
    """
    now = local_now()
    hour, minute = map(int, timestr.split(":"))

    extra_day = 0
    # Якщо "24:00" — явно наступна доба
    if hour == 24:
        hour = 0
        extra_day = 1
    # Якщо "00:00" і це кінець періоду — вважаємо наступний день
    elif hour == 0 and minute == 0 and is_end:
        extra_day = 1

    date = now.date() + timedelta(days=day_offset + extra_day)
    return TIMEZONE.localize(datetime.combine(date, time(hour, minute)))


def load_json_file(file_path: Path) -> dict:
    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error("❌ Помилка читання %s: %s", file_path, e)
        return {}

MUTE_FILE = Path("json/mute.json")
MUTE_CACHE = {}
MUTE_MTIME = None

def is_muted(channel_id: int) -> bool:
    """Повертає True, якщо для каналу встановлено mute у mute.json."""
    global MUTE_CACHE, MUTE_MTIME

    if not MUTE_FILE.exists():
        return False

    mtime = MUTE_FILE.stat().st_mtime
    if not MUTE_CACHE or mtime != MUTE_MTIME:
        try:
            with open(MUTE_FILE, "r", encoding="utf-8") as f:
                MUTE_CACHE = json.load(f)
            MUTE_MTIME = mtime
            logging.info("🔁 Оновлено mute.json")
        except Exception as e:
            logging.error(f"❌ Помилка читання mute.json: {e}")
            return False

    # Підтримка обох типів форматів (словник або список)
    if isinstance(MUTE_CACHE, dict):
        return str(channel_id) in MUTE_CACHE and bool(MUTE_CACHE[str(channel_id)])
    if isinstance(MUTE_CACHE, list):
        return channel_id in MUTE_CACHE or str(channel_id) in MUTE_CACHE
    return False


def get_post_link_for_channel(channel_id: int) -> str | None:
    """Повертає посилання на графік для каналу або None, якщо не знайдено."""
    if not POST_LINKS_FILE.exists():
        return None
    try:
        with open(POST_LINKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for entry in data:
                if entry.get("channel_id") == channel_id:
                    return entry.get("post_link")
    except Exception as e:
        logging.error(f"❌ Помилка читання post_links_today.json: {e}")
    return None


def load_schedules() -> tuple[dict, dict, bool]:
    global last_schedule_mtime, last_schedule_tomorrow_mtime, current_schedule, current_schedule_tomorrow

    changed = False

    if SCHEDULE_FILE.exists():
        mtime = SCHEDULE_FILE.stat().st_mtime
        if last_schedule_mtime is None or mtime != last_schedule_mtime:
            last_schedule_mtime = mtime
            current_schedule = load_json_file(SCHEDULE_FILE)
            logging.info("🔁 Оновлено schedule.json")
            changed = True

    if SCHEDULE_TOMORROW_FILE.exists():
        mtime_t = SCHEDULE_TOMORROW_FILE.stat().st_mtime
        if last_schedule_tomorrow_mtime is None or mtime_t != last_schedule_tomorrow_mtime:
            last_schedule_tomorrow_mtime = mtime_t
            current_schedule_tomorrow = load_json_file(SCHEDULE_TOMORROW_FILE)
            logging.info("🔁 Оновлено schedule_tomorrow.json")
            changed = True
    else:
        if current_schedule_tomorrow:
            current_schedule_tomorrow = {}
            changed = True

    return current_schedule, current_schedule_tomorrow, changed


def schedule_task(coro):
    task = asyncio.create_task(coro)
    scheduled_tasks.append(task)
    return task


def cancel_all_scheduled_tasks():
    alive = 0
    for t in scheduled_tasks:
        if not t.done():
            t.cancel()
            alive += 1
    scheduled_tasks.clear()
    if alive:
        logging.info("🛑 Скасовано %d попередніх задач(і).", alive)


# ================== SCHEDULER ==================
async def schedule_tasks_for(schedule: dict, day_offset: int = 0):
    now = local_now()
    date_str = "сьогодні" if day_offset == 0 else "завтра"
    logging.info("📅 Планування постів на %s...", date_str)

    # Якщо плануємо на сьогодні — перевіримо, чи є графік на завтра
    tomorrow_schedule = {}
    if day_offset == 0 and SCHEDULE_TOMORROW_FILE.exists():
        tomorrow_schedule = load_json_file(SCHEDULE_TOMORROW_FILE)

    for friendly_name, data in schedule.items():
        if not isinstance(data, dict):
            continue
        channel = data.get("channel_id")
        if not channel:
            continue
        periods = data.get("periods", [])

        # Якщо плануємо сьогодні і є графік на завтра для цієї черги
        tomorrow_periods = []
        if day_offset == 0 and friendly_name in tomorrow_schedule:
            tomorrow_periods = tomorrow_schedule[friendly_name].get("periods", [])

        for i, (start_str, end_str) in enumerate(periods):
            start_dt = day_timestr_to_datetime(start_str, day_offset, is_end=False)
            end_dt = day_timestr_to_datetime(end_str, day_offset, is_end=True)


            # === Перехід через північ ===
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)

            # Якщо цей період закінчується рівно о 00:00 і наступний день має 00:00 початок — об'єднати
            if tomorrow_periods:
                tomorrow_first = day_timestr_to_datetime(tomorrow_periods[0][0], 1)
                if end_dt.hour == 0 and end_dt.minute == 0 and tomorrow_first.hour == 0 and tomorrow_first.minute == 0:
                    # Вважаємо як одне тривале відключення
                    logging.info(f"🔗 Об'єднано період {friendly_name}: {start_str}-{tomorrow_periods[0][1]} через північ")
                    end_dt = day_timestr_to_datetime(tomorrow_periods[0][1], 1)
                    # Видаляємо перший період із завтрашнього
                    tomorrow_periods.pop(0)

            # Пропускаємо події, які вже минули
            if end_dt < now:
                continue

            # ⏳ Попередження за 5 хв до початку
            pre_dt = start_dt - timedelta(minutes=5)
            if pre_dt > now:
                pre_text = (
                    f"⏳ Через 5 хв відключення з {start_dt.strftime('%H:%M')} до {end_dt.strftime('%H:%M')}."
                )
                schedule_task(
                    maybe_post_message(
                        channel,
                        friendly_name,
                        pre_text,
                        pre_dt,
                        f"pre_{day_offset}",
                    )
                )

            # 🔴 Початок
            off_text = f"🔴 ВІДКЛЮЧЕННЯ з {start_dt.strftime('%H:%M')} до 💡{end_dt.strftime('%H:%M')}."
            # Додаємо посилання на пост, якщо воно є
            post_link = get_post_link_for_channel(channel)
            if post_link:
                off_text += f"\n\n📅 <b>Графік на сьогодні:</b> {post_link}"

            schedule_task(
                maybe_post_message(
                    channel,
                    friendly_name,
                    off_text,
                    start_dt,
                    f"off_{day_offset}",
                )
            )

            # 🟢 Кінець
            next_off = None

            # Якщо є наступний період сьогодні
            if i + 1 < len(periods):
                next_off = periods[i + 1][0]
            # Якщо ні — дивимось графік на завтра
            elif tomorrow_periods:
                next_off = tomorrow_periods[0][0]

            on_text = f"⚡ СВІТЛО ВМИКАЮТЬ {'об' if end_dt.hour == 11 else 'о'} {end_dt.strftime('%H:%M')}."
            if next_off:
                if day_offset == 0 and tomorrow_periods and next_off == tomorrow_periods[0][0]:
                    on_text += f"\n🔴 Наступне відключення завтра {'об' if end_dt.hour == 11 else 'о'} {next_off}"
                else:
                    on_text += f"\n🔴 Наступне відключення {'об' if end_dt.hour == 11 else 'о'} {next_off}"

            schedule_task(
                maybe_post_message(
                    channel,
                    friendly_name,
                    on_text,
                    end_dt,
                    f"on_{day_offset}",
                )
            )

    logging.info("✅ Задачі на %s створено.", date_str)


async def maybe_post_message(channel_id, friendly_name, text, send_time, event_type):
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

    # Перевіряємо mute
    if is_muted(channel_id):
        logging.info(f"🔇 Сповіщення вимкнене для каналу {channel_id}")
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

    schedule, schedule_tomorrow, _ = load_schedules()
    await schedule_tasks_for(schedule, 0)
    if schedule_tomorrow:
        await schedule_tasks_for(schedule_tomorrow, 1)

    def next_midnight(dt: datetime) -> datetime:
        return (dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    rollover_at = next_midnight(local_now())

    while True:
        await asyncio.sleep(60)
        schedule, schedule_tomorrow, changed = load_schedules()
        now = local_now()

        if changed:
            cancel_all_scheduled_tasks()

            # 🔁 Перепланування задач
            # Якщо змінився schedule.json — плануємо сьогодні
            if schedule:
                await schedule_tasks_for(schedule, 0)

            # Якщо змінився schedule_tomorrow.json — плануємо обидва, щоб оновити “завтра”
            if schedule_tomorrow:
                await schedule_tasks_for(schedule_tomorrow, 1)
                # 🔄 Також переплановуємо сьогодні, бо повідомлення “наступне завтра” могли змінитись
                await schedule_tasks_for(schedule, 0)

            rollover_at = next_midnight(now)
            continue

        if now >= rollover_at:
            cancel_all_scheduled_tasks()

            # === Переносимо розклад на завтра у сьогодні ===
            if SCHEDULE_TOMORROW_FILE.exists():
                try:
                    os.replace(SCHEDULE_TOMORROW_FILE, SCHEDULE_FILE)
                    logging.info("🔄 Замінено schedule.json новим розкладом із schedule_tomorrow.json.")
                except Exception as e:
                    logging.error(f"❌ Помилка при заміні файлів: {e}")

            # === Переносимо посилання на пости (сьогодні ← завтра) ===     
            if POST_LINKS_TOMORROW_FILE.exists():
                try:
                    os.replace(POST_LINKS_TOMORROW_FILE, POST_LINKS_FILE)
                    logging.info("🔄 Замінено post_links_today.json новим із post_links_tomorrow.json.")
                except Exception as e:
                    logging.error(f"❌ Помилка при заміні файлів постів: {e}")
            else:
                logging.warning("⚠️ Файл post_links_tomorrow.json відсутній — залишено попередній post_links_today.json.")

            # === Плануємо задачі для нового дня ===
            schedule = load_json_file(SCHEDULE_FILE)
            await schedule_tasks_for(schedule, 0)

            # === Встановлюємо наступну північ ===
            rollover_at = next_midnight(now)



if __name__ == "__main__":
    asyncio.run(main())
