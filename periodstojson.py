import json
import re
from pathlib import Path

# === Вхідний текст ===
text = """
1.1 13:00 - 15:00, 21:00 - 23:00
1.2 13:00 - 15:00, 21:00 - 23:00

2.1 07:00 - 09:00, 15:00 - 17:00
2.2 07:00 - 09:00, 15:00 - 17:00

3.1 07:00 - 09:00, 15:00 - 17:00
3.2 09:00 - 11:00, 17:00 - 19:00

4.1 09:00 - 11:00, 17:00 - 19:00
4.2 09:00 - 11:00, 17:00 - 19:00

5.1 11:00 - 13:00, 19:00 - 21:00
5.2 11:00 - 13:00, 19:00 - 21:00

6.1 11:00 - 13:00, 19:00 - 21:00
6.2 13:00 - 15:00, 21:00 - 23:00
""".strip()

# === Канали для кожної черги ===
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

# === Обробка тексту ===
result = {}
for line in text.splitlines():
    line = line.strip()
    if not line:
        continue
    match = re.match(r"^(\d+\.\d+)\s+(.+)$", line)
    if not match:
        continue
    key, periods_str = match.groups()
    periods = re.findall(r"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})", periods_str)

    result[key] = {
        "_comment": f"Черга {key}  ⚡",
        "channel_id": channel_ids.get(key, 0),
        "periods": periods
    }

# === Створюємо JSON файл ===
output_path = Path("schedule_tomorrow.json")
output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"✅ Файл '{output_path}' створено успішно.")
