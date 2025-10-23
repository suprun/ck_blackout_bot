import os
import re
import json
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from html import unescape
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# ==================== CONFIG ====================
load_dotenv()
CHANNEL_URL = os.getenv("TELEGRAM_CHANNEL_URL", "https://t.me/s/pat_cherkasyoblenergo")
MIN_DELAY = int(os.getenv("MIN_DELAY", 60))
MAX_DELAY = int(os.getenv("MAX_DELAY", 300))
PROCESSED_FILE = Path("processed.json")
LOG_FILE = os.getenv("LOG_FILE", "parser.log")
SAVE_EMPTY_AS_CHECKED = os.getenv("SAVE_EMPTY_POSTS_AS_CHECKED", "true").lower() in ("1", "true", "yes")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", 1000))

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
    # автоочистка старих
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
    """Повертає {post_id: text} з реальної структури Telegram Web."""
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
        # перетворюємо <br> на \n
        for br in text_div.find_all("br"):
            br.replace_with("\n")
        text = text_div.get_text("\n", strip=True)
        text = unescape(text)
        text = re.sub(r"\xa0", " ", text)  # non-breaking space
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
    return result


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


# ==================== MAIN LOOP ====================
def main():
    processed = load_processed()
    log.info("🚀 Парсер запущено. Очікування нових постів...")

    while True:
        try:
            html = fetch_html(CHANNEL_URL)
            posts = extract_posts_from_channel_html(html)
            if not posts:
                log.warning("⚠️ Не знайдено жодного поста на сторінці.")
            else:
                log.info(f"🔎 Знайдено {len(posts)} постів, перевіряємо нові...")

            for pid, text in sorted(posts.items()):
                if pid in processed["checked_ids"] or any(x.get("id") == pid for x in processed["published_ids"]):
                    continue

                date_obj = extract_date(text)
                schedule = parse_schedule(text)

                if not date_obj or not schedule:
                    if SAVE_EMPTY_AS_CHECKED:
                        processed["checked_ids"].append(pid)
                        save_processed(processed)
                        log.info(f"ℹ️ {pid} — немає графіка або дати, пропущено.")
                    continue

                # save schedule
                save_schedule(schedule, date_obj)

                # save as processed
                processed["published_ids"].append({
                    "id": pid,
                    "date": date_obj.strftime("%Y-%m-%d"),
                    "text_snippet": text[:300]
                })
                save_processed(processed)
                log.info(f"✅ {pid} — оброблено і збережено.")

            delay = random.randint(MIN_DELAY, MAX_DELAY)
            log.info(f"⏳ Наступна перевірка через {delay} сек.\n")
            time.sleep(delay)

        except KeyboardInterrupt:
            log.info("🛑 Зупинено вручну.")
            break
        except Exception as e:
            log.error(f"⚠️ Помилка: {e}")
            time.sleep(30)


# ==================== ENTRY ====================
if __name__ == "__main__":
    if not PROCESSED_FILE.exists():
        save_processed({"published_ids": [], "checked_ids": []})
    main()
