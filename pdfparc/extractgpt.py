# -*- coding: utf-8 -*-
"""
Парсер адрес із PDF -> SQLite (addresses_pdf)
Автор: для Vika Loychits

Що робить:
- Зчитує 11.pdf безпосередньо (через pdfplumber)
- Нормалізує текст (дефіси, пробіли, крапки)
- Сегментує за населеними пунктами (м./смт/с./селище)
- Усередині — знаходить вулиці/провулки/проспекти тощо + номери
- Діапазони чисто числові (2-6) розгортає, літери та дроби зберігає як є (10/2, 1а)
- Якщо вулиці немає, але є населений пункт — запис із пустим house_number
- Якщо адреси немає взагалі — пише всю назву в object_name
- Логи незрозумілих фрагментів: unparsed_lines.log
"""

import re
import sqlite3
from pathlib import Path
from typing import List, Tuple, Optional

import pandas as pd

PDF_FILE = "info/11.pdf"
DB_FILE = "data.db"
TABLE = "addresses_pdf"
LOG_FILE = "unparsed_lines.log"

# Якщо потрібно пересобрати таблицю з нуля у БД
DROP_TABLE_FIRST = True

# ---- Набори синонімів та патерни ----
# Типи вулиць → нормалізована форма (ключ — regex)
STREET_TYPE_MAP = {
    # UA вулиця
    r"(?i)\bвул\.?\b": "вул.",
    r"(?i)\bвулиця\b": "вул.",
    # RU "ул."
    r"(?i)\bул\.?\b": "вул.",

    # провулок
    r"(?i)\bпров\.?\b": "пров.",
    r"(?i)\bпровулок\b": "пров.",
    r"(?i)\bпрв\.?\b": "пров.",       # часто в джерелі "прв."
    r"(?i)\bпр\.(?=\s*[А-ЯІЇЄҐ])": "пров.",   # "Пр." часто = провулок (евристика)

    # проспект
    r"(?i)\bпр-т\b": "просп.",
    r"(?i)\bпросп\.?\b": "просп.",
    r"(?i)\bпроспект\b": "просп.",
    # іноді "пр." = проспект — але вище ми вже трактуємо як пров., тож не чіпаємо тут
    # (за потреби можна розрізняти за великими назвами-ознаками)

    # площа
    r"(?i)\bпл\.?\b": "площа",
    r"(?i)\bплоща\b": "площа",

    # інші
    r"(?i)\bб-р\b": "бульвар",
    r"(?i)\bбул\.?\b": "бульвар",
    r"(?i)\bбульвар\b": "бульвар",
    r"(?i)\bузвіз\b": "узвіз",
    r"(?i)\bшосе\b": "шосе",
    r"(?i)\bнабережна\b": "набережна",
    r"(?i)\bмайдан\b": "майдан",
    r"(?i)\bпроїзд\b": "проїзд",
    r"(?i)\bпроезд\b": "проїзд",
    r"(?i)\bтупик\b": "тупик",
    r"(?i)\bкільце\b": "кільце",
    r"(?i)\bтракт\b": "тракт",
}

# Населений пункт
SETTLEMENT_RE = re.compile(
    r"(?i)\b((м\.|місто|смт|с\.|село|селище)(\s+міського\s+типу)?)\s*([A-ЯІЇЄҐA-Z][\w\-'’\. ]+)",
    re.UNICODE,
)

# Розбиття сегментів усередині блоку населеного пункту (по крапках)
SPLIT_SEGMENTS_RE = re.compile(r"\.\s*")

# Токен "один номер": 10, 10а, 10/2, 10А/1
HOUSE_TOKEN_RE = re.compile(r"^\d+[А-Яа-яA-Za-z]?(/\d+)?$", re.UNICODE)

# Діапазон чисто числовий: 2-16 (або з довгим тире)
RANGE_RE = re.compile(r"^(\d+)\s*[-–—]\s*(\d+)$")

def ensure_deps():
    try:
        import pdfplumber  # noqa: F401
    except Exception:
        raise SystemExit(
            "Потрібно встановити pdfplumber: pip install pdfplumber\n"
            "Або змініть спосіб зчитування PDF у функції read_pdf_text()."
        )

def normalize_text(t: str) -> str:
    # Уніфікуємо дефіси, пробіли, прибираємо подвійні крапки
    t = t.replace("–", "-").replace("—", "-")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\u00A0", " ", t)  # NBSP
    t = t.replace(" ,", ",")
    t = re.sub(r"\s*\.\s*\.", ".", t)
    # Часто буває "вул.Забір'янська" без пробілу — вставимо логічний пробіл
    t = re.sub(r"(?i)\b(вул|ул|прв|пров|просп|пр-т|пл)\.(?=[^\s])", r"\1. ", t)
    return t

def read_pdf_text(pdf_path: str) -> str:
    import pdfplumber
    text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text(x_tolerance=1, y_tolerance=1) or ""
            text_parts.append(txt)
    return "\n".join(text_parts)

def normalize_type(token: str) -> str:
    for pat, norm in STREET_TYPE_MAP.items():
        if re.search(pat, token):
            return norm
    return ""  # невідомий/відсутній тип

def split_into_segments(addr_body: str) -> List[str]:
    segs = [s.strip(" ;,") for s in SPLIT_SEGMENTS_RE.split(addr_body) if s.strip(" ;,")]
    return segs if segs else ([addr_body.strip()] if addr_body.strip() else [])

def expand_range_token(tok: str) -> List[str]:
    m = RANGE_RE.match(tok)
    if not m:
        return [tok]
    a, b = int(m.group(1)), int(m.group(2))
    if a <= b:
        return [str(x) for x in range(a, b + 1)]
    else:
        return [str(x) for x in range(b, a + 1)]

def parse_segment(seg: str) -> Tuple[str, str, List[str], bool]:
    """
    Повертає (тип, назва_вулиці, [номери], is_address_like)
    is_address_like=True, якщо сегмент схожий на адресу (щоб відсіяти "об'єкти без адреси").
    """
    raw = seg
    seg = re.sub(r"\s+", " ", seg.strip())
    # Спроба знайти тип
    m = None
    for pat in STREET_TYPE_MAP.keys():
        m = re.search(pat, seg)
        if m:
            break

    if m:
        stype = normalize_type(m.group(0))
        after = seg[m.end():].strip()
    else:
        stype = ""  # поки не знаємо; можливо, вулиця без типу
        after = seg

    # "назва, номери" — номери часто після коми
    name_part, numbers_part = after, ""
    if "," in after:
        i = after.find(",")
        left, right = after[:i].strip(), after[i+1:].strip()
        # якщо right містить цифри — це скоріш за все номери
        if re.search(r"\d", right):
            name_part, numbers_part = left, right
        else:
            name_part = after

    # Якщо в кінці name_part є хвіст із цифрами — відщипнемо в номери
    if not numbers_part:
        tail = re.search(r"(\d.+)$", name_part)
        if tail:
            numbers_part = tail.group(1).strip(" ,")
            name_part = name_part[:tail.start()].strip(" ,")

    # Прибрати службові слова типу "буд.", "будинок"
    name_part = re.sub(r"(?i)\bбуд(\.|инок)?\b", "", name_part).strip(" ,.")

    # Розбір номерів
    house_numbers: List[str] = []
    if numbers_part:
        # Розбиваємо по комі, тримаємо дроби/літери як є, діапазони лише числові — розгортаємо
        for tok in [t.strip() for t in numbers_part.split(",") if t.strip()]:
            # нормалізуємо дефіси всередині токена
            tok = tok.replace("–", "-").replace("—", "-")
            if RANGE_RE.match(tok):
                house_numbers.extend(expand_range_token(tok))
            else:
                # 10, 10а, 10/2, 10А/1 — зберігаємо як є
                if HOUSE_TOKEN_RE.match(tok):
                    house_numbers.append(tok)
                else:
                    # щось інше — теж пишемо як є (не втрачаємо)
                    house_numbers.append(tok)

    # Якщо тип не знайдено, але назва виглядає як "ймовірна вулиця" (2+ слів, з великої)
    # — застосуємо тип за замовчуванням
    is_probably_street = bool(re.match(r"^[A-ЯІЇЄҐA-Z].{1,}$", name_part)) and not re.search(r'[«»"()]', name_part)
    if not stype and is_probably_street:
        stype = "вул."

    street_name = name_part.strip(" .,")

    # Ознака: це схоже на адресу, якщо маємо тип або "ймовірну назву вулиці"
    is_address_like = bool(stype or is_probably_street or house_numbers)

    # Якщо взагалі нічого, повертаємо як неадресний сегмент
    if not street_name and not house_numbers and not stype:
        return "", "", [], False

    return stype, street_name, house_numbers, is_address_like

def extract_settlement_spans(text: str) -> List[Tuple[int, int, str]]:
    """
    Повертає список (start_idx, end_idx, settlement_text)
    для кожного входження населеного пункту в суцільному тексті.
    """
    spans = []
    for m in SETTLEMENT_RE.finditer(text):
        spans.append((m.start(), m.end(), m.group(0).strip()))
    return spans

def segments_by_settlement(full_text: str) -> List[Tuple[Optional[str], str]]:
    """
    Розбиває увесь текст на (settlement, block_text).
    Частини до першого населеного пункту відносяться до settlement=None.
    """
    blocks: List[Tuple[Optional[str], str]] = []
    spans = extract_settlement_spans(full_text)
    if not spans:
        return [(None, full_text)]

    # Преамбула до першого нас.п.
    pre_start = 0
    first_start, first_end, first_sett = spans[0]
    if pre_start < first_start:
        blocks.append((None, full_text[pre_start:first_start].strip()))

    # Блоки між нас.п.
    for i, (s, e, sett_txt) in enumerate(spans):
        next_start = spans[i + 1][0] if i + 1 < len(spans) else len(full_text)
        block_body = full_text[e:next_start].strip()
        blocks.append((sett_txt, block_body))

    return [(sett, body) for sett, body in blocks if body]

def make_rows_from_block(settlement: Optional[str], body: str, source_name: str) -> Tuple[List[Tuple], List[str]]:
    """
    Перетворює тіло блоку населеного пункту у рядки для БД.
    Повертає (rows, unparsed_notes)
    """
    rows: List[Tuple[str, Optional[str], Optional[str], Optional[str], Optional[str]]] = []
    notes: List[str] = []

    # Ріжемо тіло на сегменти по крапках.
    segments = split_into_segments(body)
    any_address = False

    for seg in segments:
        stype, sname, nums, is_addr = parse_segment(seg)
        if is_addr and (sname or stype or nums):
            any_address = True
            street_full = f"{stype} {sname}".strip()
            if nums:
                for n in nums:
                    rows.append((source_name, settlement, street_full or None, n, None))
            else:
                rows.append((source_name, settlement, street_full or None, None, None))
        else:
            # Це не схоже на адресу — йде у object_name (як "об’єкт без адреси")
            # Але збережемо і в лог для контролю
            clean = seg.strip(" ,;")
            if clean:
                rows.append((source_name, settlement, None, None, clean))
                notes.append(f"[{settlement or '-'}] OBJ: {clean}")

    # Якщо жодного сегмента не розпізнали як адресу, але був settlement — усе вже пішло як object_name
    return rows, notes

def main():
    # 1) Перевірка залежностей і PDF
    ensure_deps()
    pdf_path = Path(PDF_FILE)
    if not pdf_path.exists():
        raise SystemExit(f"Не знайдено {PDF_FILE}")

    # 2) Зчитати PDF у текст і нормалізувати
    full_raw = read_pdf_text(PDF_FILE)
    full_txt = normalize_text(full_raw)

    # 3) Розбити на блоки за населеними пунктами
    blocks = segments_by_settlement(full_txt)

    # 4) Підготуємо БД
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    if DROP_TABLE_FIRST:
        cur.execute(f"DROP TABLE IF EXISTS {TABLE}")
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT,
            settlement TEXT,
            street TEXT,
            house_number TEXT,
            object_name TEXT
        )
    """)
    # перезапис вмісту
    cur.execute(f"DELETE FROM {TABLE}")
    conn.commit()

    # 5) Розбір блоків і запис
    # У PDF немає явного "source_name" для кожного блоку — візьмемо з лівої частини settlement
    # або з ключових слів у блоці. Для простоти — використовуємо сам settlement як source_name,
    # а для преамбули None — "Загальний список" (можете замінити на іншу логіку).
    unparsed: List[str] = []
    batch = []
    for sett, body in blocks:
        source_name = (sett or "Загальний список").strip()
        rows, notes = make_rows_from_block(sett, body, source_name)
        unparsed.extend(notes)
        batch.extend(rows)
        if len(batch) >= 3000:
            cur.executemany(
                f"INSERT INTO {TABLE} (source_name, settlement, street, house_number, object_name) VALUES (?,?,?,?,?)",
                batch
            )
            conn.commit()
            batch.clear()

    if batch:
        cur.executemany(
            f"INSERT INTO {TABLE} (source_name, settlement, street, house_number, object_name) VALUES (?,?,?,?,?)",
            batch
        )
        conn.commit()

    conn.close()

    # 6) Лог нерозібраних фрагментів/об’єктів
    if unparsed:
        Path(LOG_FILE).write_text("\n".join(unparsed), encoding="utf-8")

    # 7) Експорт короткого підсумку
    df = pd.DataFrame(batch, columns=["source_name", "settlement", "street", "house_number", "object_name"])
    print("✅ Готово. Таблиця:", TABLE, "у", DB_FILE)
    print("   Рядків (в цій сесії batch):", len(df))
    if unparsed:
        print(f"   Лог незрозумілих/безадресних сегментів: {LOG_FILE} (рядків: {len(unparsed)})")
    else:
        print("   Незрозумілих сегментів не виявлено.")

if __name__ == "__main__":
    main()
