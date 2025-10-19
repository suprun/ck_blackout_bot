# -*- coding: utf-8 -*-
"""
parse_pdf_multi.py
Парсить кілька PDF-файлів з таблицями відключень у єдину базу SQLite.
Підтримує розпізнавання адрес, діапазонів будинків, назв об'єктів та джерело файлу.
"""

import re
import sqlite3
import csv
import sys
import pdfplumber

# === Налаштування ===
inf="info/"
PDF_FILES = [
    f"{inf}11.pdf",
    f"{inf}12.pdf",
    f"{inf}21.pdf",
    f"{inf}22.pdf",
    f"{inf}31.pdf",
    f"{inf}32.pdf",
    f"{inf}41.pdf",
    f"{inf}42.pdf",
    f"{inf}51.pdf",
    f"{inf}52.pdf",
    f"{inf}61.pdf",
    f"{inf}62.pdf"    # додай сюди інші PDF-файли, які потрібно обробити
    # "obl_main_static_173_Зима-25-26.pdf",
    # "obl_main_static_174_Весна-26.pdf",
]
OUT_DB = "outages_multi.db"
UNCLASSIFIED_CSV = "unclassified_segments.csv"

# ключові патерни
SUBSTATION_KEYWORDS = ["філія", "всп", "ем", "відділення", "відділ", "філіал"]
ORG_KEYWORDS = ['ФОП', 'ТОВ', 'ПП', 'АТ', 'КП', 'КНП', 'ПСП', 'СТОВ', 'ФГ', 'СФГ', 'ОТГ', 'Філія', 'Парафія']
HEADER_PATTERNS = ["Назва підстанцій", "Перелік основних відключаємих споживачів",
                   "Графік погодинного відключення", "Страница", "1_черга", "черга"]
STREET_KEYS_RE = r"(вул\.?|вулиц[яі]|вул[\.]?)"
LOCALITY_KEYS_RE = r"(м\.|м\b|смт\.|смт\b|с\.|с\b|х\.|хутір\b)"
NUM_RE = r"\d{1,4}"

# інші параметри
EXPAND_RANGES = True
MAX_EXPAND_RANGE = 200
MAX_SUBSTATION_COMMAS = 2
MAX_SUBSTATION_LEN = 100


# === Ініціалізація БД ===
conn = sqlite3.connect(OUT_DB)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS outages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT,
    substation TEXT,
    locality TEXT,
    street TEXT,
    house_number TEXT,
    object_name TEXT,
    raw_segment TEXT
)
""")
conn.commit()


# === Утиліти ===
def clean(s: str) -> str:
    if s is None:
        return None
    s = s.replace('\xa0', ' ')
    s = re.sub(r'\s+', ' ', s)
    return s.strip(" \t\n\r,;:.—-")

def is_header(line: str) -> bool:
    low = line.lower()
    for h in HEADER_PATTERNS:
        if h.lower() in low:
            return True
    if re.match(r"Страница\s*\d+", line):
        return True
    return False

def contains_address_hint(line: str) -> bool:
    return bool(re.search(STREET_KEYS_RE, line, flags=re.IGNORECASE) or
                re.search(LOCALITY_KEYS_RE, line, flags=re.IGNORECASE) or
                re.search(NUM_RE, line))

def looks_like_substation(line: str) -> bool:
    low = line.lower()
    if not any(k in low for k in SUBSTATION_KEYWORDS):
        return False
    if contains_address_hint(line):
        return False
    if line.count(",") > MAX_SUBSTATION_COMMAS:
        return False
    if len(line) > MAX_SUBSTATION_LEN:
        return False
    return True

def split_mixed(line: str):
    markers = []
    for m in re.finditer(STREET_KEYS_RE, line, flags=re.IGNORECASE):
        markers.append(m.start())
    for m in re.finditer(LOCALITY_KEYS_RE, line, flags=re.IGNORECASE):
        markers.append(m.start())
    for m in re.finditer(r'\b\d{1,4}\b', line):
        markers.append(m.start())
    if not markers:
        return line, None
    first = min(markers)
    left = clean(line[:first])
    right = clean(line[first:])
    if any(k.lower() in left.lower() for k in ORG_KEYWORDS):
        return left, right
    return line, None

def split_segments(line: str):
    l = line.replace('—', ' - ').replace('–', ' - ')
    parts = re.split(r'\s*;\s*|\s*\-\s*|\s*—\s*', l)
    out = []
    for p in parts:
        if ':' in p:
            left, right = p.split(':', 1)
            left, right = left.strip(), right.strip()
            if left:
                out.append(left + ':')
            if right:
                out.extend([x.strip() for x in right.split(',') if x.strip()])
        else:
            if p.count(',') >= 2:
                out.extend([x.strip() for x in p.split(',') if x.strip()])
            else:
                out.append(p.strip())
    return [clean(x) for x in out if x and not is_header(x)]

def expand_number_token(locality, street, token, rawseg):
    token = token.replace('–', '-')
    if '-' in token:
        parts = token.split('-')
        try:
            start = int(re.sub(r'\D.*$', '', parts[0]))
            end = int(re.sub(r'\D.*$', '', parts[1]))
        except:
            return [(locality, street, token, rawseg)]
        span = end - start + 1
        if EXPAND_RANGES and 0 < span <= MAX_EXPAND_RANGE:
            return [(locality, street, str(n), rawseg) for n in range(start, end + 1)]
        return [(locality, street, f"{start}-{end}", rawseg)]
    else:
        return [(locality, street, token, rawseg)]

def parse_streets_from_segment(seg: str, default_locality=None):
    seg_raw = seg
    res = []
    pattern = re.compile(r'(' + STREET_KEYS_RE + r')\s*([^\d,;:]+)', flags=re.IGNORECASE)
    matches = list(pattern.finditer(seg))
    if matches:
        for i, m in enumerate(matches):
            street_name = clean(m.group(2))
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(seg)
            tail = seg[start:end].strip(" ,;:")
            numbers = re.findall(r'\d+(?:[\/\-\–]\d+)?(?:[а-яa-zA-ZА-ЯІіЇїЄєҐґ])?', tail)
            if numbers:
                for n in numbers:
                    res.extend(expand_number_token(default_locality, street_name, n, seg_raw))
            else:
                res.append((default_locality, street_name, None, seg_raw))
        return res
    # альтернатива: "Лівобережна 2-16"
    parts = [p.strip() for p in re.split(r',\s*', seg) if p.strip()]
    for p in parts:
        m2 = re.match(r'(.+?)\s+(\d+(?:[\/\-\–]\d+)?(?:[а-яa-zA-ZА-ЯІіЇїЄєҐґ])?)$', p)
        if m2:
            sname, num = clean(m2.group(1)), clean(m2.group(2))
            res.extend(expand_number_token(default_locality, sname, num, seg_raw))
        else:
            res.append((default_locality, clean(p), None, seg_raw))
    return res

def split_orgs(seg: str):
    parts = [p.strip() for p in re.split(r',\s*', seg) if p.strip()]
    orgs = []
    for p in parts:
        if any(k.lower() in p.lower() for k in ORG_KEYWORDS) or '"' in p or len(p) >= 10:
            orgs.append(clean(p))
    return orgs

def insert_row(source_file, sub, loc, street, number, obj, raw):
    cur.execute("""
        INSERT INTO outages(source_file, substation, locality, street, house_number, object_name, raw_segment)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (source_file, sub, loc, street, number, obj, raw))
    conn.commit()

def print_progress(prefix, current, total, width=40):
    frac = current / total if total else 1.0
    filled = int(width * frac)
    bar = "[" + "#" * filled + "-" * (width - filled) + "]"
    sys.stdout.write(f"\r{prefix} {bar} {current}/{total}")
    sys.stdout.flush()
    if current == total:
        sys.stdout.write("\n")

# === Основна логіка ===
def parse_single_pdf(path, source_name):
    unclassified = []
    inserted = 0
    with pdfplumber.open(path) as pdf:
        total_pages = len(pdf.pages)
        curr_sub, curr_loc = None, None
        for pidx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            lines = [l for l in text.split("\n") if l.strip()]
            for raw_line in lines:
                line = clean(raw_line)
                if not line or is_header(line):
                    continue
                if looks_like_substation(line):
                    curr_sub, curr_loc = line, None
                    continue
                left, right = split_mixed(line)
                segs = split_segments(right if right else line)
                if right:
                    orgs = split_orgs(left)
                    for o in orgs:
                        insert_row(source_name, curr_sub, None, None, None, o, left)
                        inserted += 1
                for seg in segs:
                    if not seg:
                        continue
                    mloc = re.search(LOCALITY_KEYS_RE + r'\s*([^\.,;:]+)', seg, flags=re.IGNORECASE)
                    if mloc:
                        curr_loc = clean(mloc.group(1))
                        if seg.strip().endswith(':'):
                            continue
                    if contains_address_hint(seg):
                        items = parse_streets_from_segment(seg, curr_loc)
                        if items:
                            for lcl, st, num, rawseg in items:
                                insert_row(source_name, curr_sub, lcl, st, num, None, rawseg)
                                inserted += 1
                        else:
                            unclassified.append((source_name, curr_sub, seg))
                    else:
                        orgs = split_orgs(seg)
                        if orgs:
                            for o in orgs:
                                insert_row(source_name, curr_sub, None, None, None, o, seg)
                                inserted += 1
                        else:
                            unclassified.append((source_name, curr_sub, seg))
            print_progress(f"{source_name}", pidx, total_pages)
    return inserted, unclassified

def parse_pdfs(pdf_list):
    total_inserted = 0
    all_unclassified = []
    for path in pdf_list:
        source_name = path.split("/")[-1]
        print(f"\n=== Обробка файлу: {source_name} ===")
        inserted, uncls = parse_single_pdf(path, source_name)
        total_inserted += inserted
        all_unclassified.extend(uncls)
        print(f"  ✔ {inserted} записів, {len(uncls)} невпізнаних")
    # Збереження невпізнаних
    if all_unclassified:
        with open(UNCLASSIFIED_CSV, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["source_file", "substation", "raw_segment"])
            for row in all_unclassified:
                w.writerow(row)
    print(f"\n✅ Загалом вставлено {total_inserted} записів.")
    print(f"❕ Невпізнані сегменти збережено у {UNCLASSIFIED_CSV}")

# === Запуск ===
if __name__ == "__main__":
    parse_pdfs(PDF_FILES)
    conn.close()
    print("\nГотово! Дані збережено у базі:", OUT_DB)
