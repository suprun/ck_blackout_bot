import re
import json
from datetime import datetime, timedelta
from pathlib import Path

# === Текст поста (сюди вставляй новий пост) ===
text = """
Оновлений графік ГПВ на 23 жовтня з 14:00 до 23:00 по Черкаській області.

Години відсутності електропостачання по чергам (підчергам):

1.1 19:00 - 21:00
1.2 19:00 - 21:00

3.1 14:00 - 15:00, 21:00 - 23:00
3.2 14:00 - 15:00, 21:00 - 23:00

4.1 15:00 - 17:00
4.2 15:00 - 17:00

6.1 17:00 - 19:00
6.2 17:00 - 19:00
""".strip()


# === Словник каналів ===
channel_ids = {
    "1.1": -1003113234171,
    "1.2": -1003145633887,
    "2.1": -1003147594459,
    "2.2": -1003138079087,
    "3.1": -1003128920788,
    "3.2": -1002967860214,
    "4.1": -1003033893922,
    "4.2": -1003009930050,
    "5.1": -1003170499896,
    "5.2": -1003096266337,
    "6.1": -1003169834725,
    "6.2": -1002988126895,
}


# === Визначення дати в тексті ===
month_map = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6,
    "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12
}

date_match = re.search(r"(\d{1,2})\s+(січня|лютого|березня|квітня|травня|червня|липня|серпня|вересня|жовтня|листопада|грудня)", text, re.IGNORECASE)
target_date = None

if date_match:
    day = int(date_match.group(1))
    month_name = date_match.group(2).lower()
    month = month_map.get(month_name)
    now = datetime.now()  # поточна дата за київським часом
    year = now.year
    # якщо місяць вже минув (наприклад, грудень, а зараз січень), то рік +1
    if month < now.month - 6:
        year += 1
    target_date = datetime(year, month, day)
    print(f"📅 Знайдена дата у тексті: {target_date.strftime('%d.%m.%Y')}")

# === Визначаємо сьогодні чи завтра ===
today = datetime.now().date()
file_name = "schedule.json"
if target_date:
    if target_date.date() == today + timedelta(days=1):
        file_name = "schedule_tomorrow.json"
    elif target_date.date() != today:
        file_name = f"schedule_{target_date.strftime('%d%m')}.json"  # запасний варіант
print(f"📁 Буде створено файл: {file_name}")

# === Витягуємо графік черг ===
result = {}
for line in text.splitlines():
    line = line.strip()
    if not re.match(r"^\d+\.\d+", line):
        continue
    match = re.match(r"^(\d+\.\d+)\s+(.+)$", line)
    if not match:
        continue
    key, periods_str = match.groups()
    periods = re.findall(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", periods_str)
    result[key] = {
        "_comment": f"Черга {key} ⚡",
        "channel_id": channel_ids.get(key, 0),
        "periods": periods
    }

# === Зберігаємо у JSON ===
if result:
    Path(file_name).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Файл '{file_name}' створено ({len(result)} черг).")
else:
    print("⚠️ Не знайдено жодного графіка у тексті.")
