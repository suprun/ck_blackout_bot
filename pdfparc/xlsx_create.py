# -*- coding: utf-8 -*-
import pdfplumber
import pandas as pd
import re
from collections import OrderedDict

pdf_path = "info/11.pdf"
out_xlsx = "output_cleaned.xlsx"

# --- Патерни для видалення службових фраз ---
header_patterns = [
    r"Назва підстанцій[^\n]*Перелік основних відключаємих споживачів",
    r"Графік погодинного відключення[^\n]*Черкаської області",
    r"Страница\s*\d+"
]

remove_patterns = [
    r"Графік погодинного відключення електричної енергії.*Черкаської області",
    r"Назва підстанцій,?\s*об'?єктів\s*Перелік основних відключаємих споживачів",
    r"1\s*черга.*підчерга",
]

# --- Пошук назв підрозділів лише у першому стовпці ---
section_regex = re.compile(r"\b(філія|всп|ем|відділення)\b", flags=re.IGNORECASE | re.UNICODE)

sections = OrderedDict()
current_section = None

def clean_cell(text):
    """Очищення комірки від службових фраз і пробілів"""
    if text is None:
        return ""
    txt = str(text).strip()
    for p in header_patterns:
        txt = re.sub(p, " ", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt

with pdfplumber.open(pdf_path) as pdf:
    for page_num, page in enumerate(pdf.pages, start=1):
        tables = page.extract_tables()
        if not tables:
            continue

        for table in tables:
            for row in table:
                row = [("" if c is None else c) for c in row]
                first = clean_cell(row[0]) if len(row) > 0 else ""

                if first and section_regex.search(first):
                    section_name = first
                    rest = " ".join(clean_cell(c) for c in row[1:]).strip()
                    if section_name not in sections:
                        sections[section_name] = []
                    if rest:
                        sections[section_name].append(rest)
                    current_section = section_name
                else:
                    if current_section:
                        joined = " ".join(clean_cell(c) for c in row if clean_cell(c))
                        if joined:
                            sections[current_section].append(joined)

# --- Формуємо попередній DataFrame ---
rows = []
for sec, texts in sections.items():
    combined = " ; ".join(t for t in texts if t).strip()
    combined = re.sub(r"\s{2,}", " ", combined)
    rows.append({"Підрозділ": sec, "Перелік": combined})

df = pd.DataFrame(rows)

# --- Очищення "Переліку" від службових фраз ---
def clean_text(text):
    if pd.isna(text):
        return ""
    t = str(text)
    for p in remove_patterns:
        t = re.sub(p, " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s{2,}", " ", t).strip(" ;,")
    return t

df["Перелік"] = df["Перелік"].apply(clean_text)

# --- Видалення порожніх рядків і дублікатів підрозділів ---
df = df[df["Перелік"].str.strip() != ""]
df = df.groupby("Підрозділ", as_index=False)["Перелік"].apply(lambda x: " ".join(x)).drop_duplicates()

# --- Збереження результату ---
df.to_excel(out_xlsx, index=False)

print(f"✅ Готово! Створено чистий Excel: {out_xlsx}")
print(f"Знайдено підрозділів: {len(df)}")
