import os
import re
import json
import time
import random
import logging
import subprocess
import asyncio
import requests
from bs4 import BeautifulSoup
from html import unescape
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from telegram import Bot  # pip install python-telegram-bot==20.8

# ==================== CONFIG ====================
load_dotenv()
CHANNEL_URL = os.getenv("TELEGRAM_CHANNEL_URL", "https://t.me/s/pat_cherkasyoblenergo")
MIN_DELAY = int(os.getenv("MIN_DELAY", 60))
MAX_DELAY = int(os.getenv("MAX_DELAY", 300))
PROCESSED_FILE = Path("processed.json")
LOG_FILE = os.getenv("LOG_FILE", "parser.log")
SAVE_EMPTY_AS_CHECKED = os.getenv("SAVE_EMPTY_POSTS_AS_CHECKED", "true").lower() in ("1", "true", "yes")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", 1000))
BOT_TOKEN = os.getenv("TEST_BOT_TOKEN")  # токен бота для постингу

bot = Bot(token=BOT_TOKEN) if BOT_TOKEN else None

CHANNEL_IDS = {
    "1.1": -1003113234171, "1.2": -1003145633887,
    "2.1": -1003147594459, "2.2": -1003138079087,
    "3.1": -1003128920788, "3.2": -1002967860214,
    "4.1": -1003033893922, "4.2": -1003009930050,
    "5.1": -1003170499896, "5.2": -1003096266337,
    "6.1": -1003169834725, "6.2": -1002988126895,
}

MONTHS = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4,
    "травня": 5, "червня": 6, "липня": 7, "серпня": 8,
    "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12,
}

# ==================== LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("parser")


# ==================== HELPERS ====================
def load_processed():
    if PROCESSED_FILE.exists():
        try:
            data = json.loads(PROCESSED_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {"published_ids": [], "checked_ids": []}
    else:
        data = {"published_ids": [], "checked_ids": []}
    data.setdefault("published_ids", [])
    data.setdefault("checked_ids", [])
    return data


def save_processed(data):
    for key in ["published_ids", "checked_ids"]:
        if len(data[key]) > MAX_HISTORY:
            data[key] = data[key][-MAX_HISTORY:]
    PROCESSED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_html(url):
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TelegramParser/1.0)"}
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.text


def extract_posts_from_channel_html(html: str):
    """Парсить реальну структуру Telegram Web."""
    soup = BeautifulSoup(html, "html.parser")
    posts = {}
    for msg_div in soup.find_all("div", class_="tgme_widget_message"):
        post_raw = msg_div.get("data-post")
        if not post_raw:
            continue
        post_id = post_raw.replace("/", "_")
        text_div = msg_div.find("div", class_="tgme_widget_message_text")
        if not text_div:
            continue
        for br in text_div.find_all("br"):
            br.replace_with("\n")
        text = text_div.get_text("\n", strip=True)
        text = unescape(text)
        text = re.sub(r"\xa0", " ", text)
        posts[post_id] = text.strip()
    return posts


def extract_date(text: str):
    m = re.search(r"(\d{1,2})\s+(січня|лютого|березня|квітня|травня|червня|липня|серпня|вересня|жовтня|листопада|грудня)", text, re.I)
    if not m:
        return None
    day = int(m.group(1))
    month = MONTHS[m.group(2).lower()]
    now = datetime.now()
    year = now.year
    if month < now.month - 6:
        year += 1
    return datetime(year, month, day)


def parse_schedule(text: str):
    result = {}
    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not re.match(r"^\d+\.\d+", line):
            continue
        m = re.match(r"^(\d+\.\d+)\s+(.+)$", line)
        if not m:
            continue
        key, rest = m.groups()
        periods = re.findall(r"(\d{1,2}:\d{2})\s*[-–—]\s*(\d{1,2}:\d{2})", rest)
        if not periods:
            periods = re.findall(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", rest)
        if periods:
            result[key] = {
                "_comment": f"Черга {key} ⚡",
                "channel_id": CHANNEL_IDS.get(key, 0),
                "periods": periods
            }
            periods_text = ", ".join(f"{a} - {b}" for a, b in periods)
            lines.append(f"{key} {periods_text}")
    return result, "\n".join(lines)


def save_schedule(schedule, date_obj):
    today = datetime.now().date()
    if date_obj.date() == today:
        filename = "schedule.json"
    elif date_obj.date() == today + timedelta(days=1):
        filename = "schedule_tomorrow.json"
    else:
        filename = f"schedule_{date_obj.strftime('%d%m')}.json"
    Path(filename).write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"✅ Збережено {filename} ({len(schedule)} черг)")
    return filename


def create_schedule_txt(schedule_txt: str):
    Path("schedule.txt").write_text(schedule_txt, encoding="utf-8")
    log.info("📝 Створено schedule.txt")


def create_table_date_file(date_obj):
    """Створює tabledate.txt із датою '24 жовтня, п’ятниця'."""
    weekdays = [
        "понеділок", "вівторок", "середа",
        "четвер", "п’ятниця", "субота", "неділя"
    ]
    months = [
        "", "січня", "лютого", "березня", "квітня", "травня", "червня",
        "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"
    ]
    weekday_name = weekdays[date_obj.weekday()]
    month_name = months[date_obj.month]
    formatted = f"{date_obj.day} {month_name}, {weekday_name}"
    Path("tabledate.txt").write_text(formatted, encoding="utf-8")
    log.info(f"📅 Створено tabledate.txt: {formatted}")


def run_createtabletem():
    log.info("🎨 Запускаємо createtabletem.py ...")
    try:
        result = subprocess.run(
            ["python3", "createtabletem.py"],
            capture_output=True,
            text=True,
            check=True,
            timeout=60
        )
        log.info("🖼️ createtabletem.py завершився успішно.")
        if result.stdout:
            log.debug(f"[stdout] {result.stdout.strip()}")
        if result.stderr:
            log.debug(f"[stderr] {result.stderr.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"❌ createtabletem.py завершився з кодом {e.returncode}")
        log.error(f"[stderr]: {e.stderr.strip() if e.stderr else '---'}")
        return False
    except subprocess.TimeoutExpired:
        log.error("⏱️ createtabletem.py завис (timeout).")
        return False
    except Exception as e:
        log.error(f"⚠️ Помилка при запуску createtabletem.py: {e}")
        return False


# === Асинхронне надсилання зображення ===
async def send_image_to_channels_async(post_text: str, schedule_txt: str):
    if not bot:
        log.warning("⚠️ BOT_TOKEN не вказано — публікація пропущена.")
        return

    test_mode = os.getenv("TEST_MODE", "false").lower() in ("1", "true", "yes")
    if test_mode:
        test_ids_str = os.getenv("TEST_CHANNEL_IDS", "")
        channels = [int(x.strip()) for x in test_ids_str.split(",") if x.strip()]
        log.info(f"🧪 TEST_MODE активний. Надсилаємо у тестові канали: {channels}")
    else:
        channels = CHANNEL_IDS.values()

    prefix = post_text.split("1.1")[0].strip() if "1.1" in post_text else post_text[:200]
    prefix = prefix.replace(
        "Години відсутності електропостачання по чергам (підчергам):", ""
    ).strip()
    caption = f"{prefix}\n\n{schedule_txt}\n\n💡Сповіщення про відключення по всім чергам тут: @ck_blackout_bot\""

    for ch_id in channels:
        try:
            with open("colored.png", "rb") as img:
                await bot.send_photo(chat_id=ch_id, photo=img, caption=caption)
            log.info(f"📤 Зображення надіслано у канал {ch_id}")
        except Exception as e:
            log.error(f"❌ Помилка надсилання у {ch_id}: {e}")


def send_image_to_channels(post_text: str, schedule_txt: str):
    asyncio.run(send_image_to_channels_async(post_text, schedule_txt))


# ==================== MAIN LOOP ====================
def main():
    processed = load_processed()
    log.info("🚀 Парсер запущено. Очікування нових постів...")

    while True:
        try:
            html = fetch_html(CHANNEL_URL)
            posts = extract_posts_from_channel_html(html)
            log.info(f"🔎 Знайдено {len(posts)} постів.")

            for pid, text in sorted(posts.items()):
                if pid in processed["checked_ids"] or any(x.get("id") == pid for x in processed["published_ids"]):
                    continue

                date_obj = extract_date(text)
                schedule, schedule_txt = parse_schedule(text)

                if not date_obj or not schedule:
                    if SAVE_EMPTY_AS_CHECKED:
                        processed["checked_ids"].append(pid)
                        save_processed(processed)
                        log.info(f"ℹ️ {pid} — немає графіка або дати, пропущено.")
                    continue

                save_schedule(schedule, date_obj)
                create_table_date_file(date_obj)
                create_schedule_txt(schedule_txt)

                if run_createtabletem():
                    send_image_to_channels(text, schedule_txt)
                else:
                    log.warning("⚠️ Зображення не створено, публікація пропущена.")

                processed["published_ids"].append({
                    "id": pid,
                    "date": date_obj.strftime("%Y-%m-%d"),
                    "text_snippet": text[:300]
                })
                save_processed(processed)
                log.info(f"✅ {pid} — оброблено й опубліковано.")

            delay = random.randint(MIN_DELAY, MAX_DELAY)
            log.info(f"⏳ Наступна перевірка через {delay} сек.\n")
            time.sleep(delay)

        except KeyboardInterrupt:
            log.info("🛑 Зупинено вручну.")
            break
        except Exception as e:
            log.error(f"⚠️ Помилка: {e}")
            time.sleep(30)


if __name__ == "__main__":
    if not PROCESSED_FILE.exists():
        save_processed({"published_ids": [], "checked_ids": []})
    main()
