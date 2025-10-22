import os
import time
import json
import re
import hashlib
import random
import requests
from bs4 import BeautifulSoup
from telegram import Bot
from dotenv import load_dotenv
from datetime import datetime
from json import JSONDecodeError

# === завантажуємо змінні середовища ===
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_IDS = [int(x.strip()) for x in os.getenv("CHANNEL_IDS", "").split(",") if x.strip()]

TRIGGERS_FILE = "web_triggers.json"
STATE_FILE = "web_parser_state.json"
LOG_FILE = "web_parser.log"

bot = Bot(token=BOT_TOKEN)


# === безпечне збереження JSON ===
def safe_save_json(data, filename):
    tmp = filename + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())  # гарантуємо запис на диск
        os.replace(tmp, filename)  # атомарна заміна
    except Exception as e:
        print(f"[ERROR] Не вдалося записати {filename}: {e}")


# === логування ===
def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# === завантаження словників ===
def load_triggers():
    if not os.path.exists(TRIGGERS_FILE):
        default = {
            "global_triggers": ["відключення", "аварія", "електроенергія"],
            "channel_triggers": {str(ch): [] for ch in CHANNEL_IDS},
            "source_channels": ["https://t.me/pat_cherkasyoblenergo"]
        }
        with open(TRIGGERS_FILE, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
        return default
    with open(TRIGGERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

triggers = load_triggers()


# === безпечне завантаження стану ===
def load_state():
    if not os.path.exists(STATE_FILE):
        return {"seen_hashes": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (JSONDecodeError, OSError) as e:
        log(f"⚠️ state.json пошкоджено ({e}), створюю новий.")
        backup = STATE_FILE + ".corrupt_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            os.rename(STATE_FILE, backup)
        except Exception:
            pass
        return {"seen_hashes": []}


state = load_state()


# === утиліти ===
def save_state():
    safe_save_json(state, STATE_FILE)

def contains_trigger(text, phrases):
    text_low = text.lower()
    for p in phrases:
        if re.search(re.escape(p.lower()), text_low):
            return True
    return False

def hash_message(text, date_str):
    return hashlib.sha256(f"{date_str}|{text}".encode("utf-8")).hexdigest()


# === парсинг публічної веб-версії каналу ===
def parse_channel(url):
    # рандомна коротка затримка перед кожним запитом
    delay = random.randint(2, 10)
    time.sleep(delay)
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        log(f"❌ Не вдалося завантажити {url}: {e}")
        return []

    soup = BeautifulSoup(resp.content, "html.parser")
    msgs = []
    for mdiv in soup.find_all("div", class_="tgme_widget_message"):
        txt = ""
        t_el = mdiv.find("div", class_="tgme_widget_message_text")
        if t_el:
            txt = t_el.get_text(separator="\n", strip=True)
        date_el = mdiv.find("time")
        date_str = date_el["datetime"] if date_el and date_el.has_attr("datetime") else ""
        msgs.append({"text": txt, "date": date_str})
    return msgs


# === обробка повідомлень ===
def process_messages():
    for url in triggers["source_channels"]:
        log(f"🔍 Перевірка каналу {url}")
        msgs = parse_channel(url)
        for m in msgs:
            if not m["text"]:
                continue

            h = hash_message(m["text"], m["date"])
            if h in state["seen_hashes"]:
                continue  # уже бачили

            # нове повідомлення
            state["seen_hashes"].append(h)
            if len(state["seen_hashes"]) > 1000:
                state["seen_hashes"] = state["seen_hashes"][-1000:]
            save_state()

            text = m["text"]
            log(f"🆕 Нове повідомлення: {text[:80]}...")

            # --- глобальні тригери ---
            if contains_trigger(text, triggers["global_triggers"]):
                for ch in CHANNEL_IDS:
                    try:
                        bot.send_message(ch, text)
                        log(f"✅ Global trigger → {ch}")
                    except Exception as e:
                        log(f"❌ Помилка надсилання у {ch}: {e}")
                continue

            # --- тригери для конкретних каналів ---
            for ch in CHANNEL_IDS:
                key = str(ch)
                if key in triggers["channel_triggers"]:
                    if contains_trigger(text, triggers["channel_triggers"][key]):
                        try:
                            bot.send_message(ch, text)
                            log(f"✅ Channel trigger {key} → {ch}")
                        except Exception as e:
                            log(f"❌ Помилка надсилання у {ch}: {e}")
                        break


# === головний цикл із випадковими інтервалами ===
def run_loop():
    log("🚀 Запуск парсера з випадковими інтервалами (60–120 сек)...")
    while True:
        try:
            process_messages()
        except Exception as e:
            log(f"⚠️ Помилка в process_messages: {e}")

        wait_sec = random.randint(60, 120)
        log(f"💤 Очікування {wait_sec} сек до наступної перевірки...")
        time.sleep(wait_sec)


# === запуск у фоні з основного бота ===
def start_parser_async():
    import threading
    t = threading.Thread(target=run_loop, daemon=True)
    t.start()
    log("🧩 Фоновий парсер запущено")


if __name__ == "__main__":
    run_loop()
