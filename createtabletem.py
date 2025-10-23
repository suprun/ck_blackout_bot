#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from lxml import etree
from pathlib import Path
import cairosvg
from PIL import Image, ImageDraw, ImageFont
import re

# === ШЛЯХИ ===
INPUT_TEXT = Path("schedule.txt")      # текст із розкладом
SVG_TEMPLATE = Path("template.svg")    # SVG-шаблон
OUTPUT_SVG = Path("colored.svg")
OUTPUT_PNG = Path("colored.png")

# === ПАРАМЕТРИ ===
COLOR_ON = "#646E7D"      # колір відключення
COLOR_OFF = "#FFDD1F"     # колір нормального стану
TEXT = "23 жовтня, четвер" # текст для підпису
TEXT_COLOR = "#222222"     # колір тексту
FONT_PATH = Path("RoadUI-SemiBold.otf") # шлях до файлу шрифту
FONT_SIZE = 28             # розмір шрифту
TEXT_POSITION = "bottom"   # "top" або "bottom"
QUEUE_PATTERN = re.compile(r"^(\d+\.\d+)\s+(.+)$")

# ---------------------------------------------------------------
def parse_schedule_text(text: str) -> dict:
    """Парсить текст розкладу у форматі типу: 1.1 11:00 - 13:00, 19:00 - 21:00"""
    result = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = QUEUE_PATTERN.match(line)
        if not m:
            continue
        queue_id, intervals_raw = m.groups()
        parts = [x.strip() for x in intervals_raw.split(",") if x.strip()]
        intervals = []
        for part in parts:
            if "-" not in part:
                continue
            start, end = [t.strip() for t in part.split("-")]
            intervals.append((start, end))
        result[queue_id] = intervals
    return result


def get_halfhour_ids(queue_id: str, intervals: list) -> list:
    """Перетворює інтервали у список id блоків {queue_id}_{hh}{a|b}"""
    ids = []
    for start, end in intervals:
        h1, m1 = map(int, start.split(":"))
        h2, m2 = map(int, end.split(":"))
        start_min = h1 * 60 + m1
        end_min = h2 * 60 + m2
        for t in range(start_min, end_min, 30):
            hour = (t // 60) % 24
            half = "a" if (t % 60) < 30 else "b"
            ids.append(f"{queue_id}_{hour:02d}{half}")
    return ids


def recolor_svg(svg_path: Path, colored_ids: set, color_on: str, color_off: str) -> bytes:
    """Фарбує SVG: усі блоки -> color_off, потрібні ID -> color_on"""
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(svg_path), parser)
    root = tree.getroot()

    all_rects = root.xpath("//*[@id]")
    for el in all_rects:
        el_id = el.get("id")
        if not el_id:
            continue
        color = color_on if el_id in colored_ids else color_off
        el.set("fill", color)
        style = el.get("style")
        if style:
            parts = style.split(";")
            parts = [p for p in parts if not p.strip().startswith("fill:")]
            parts.append(f"fill:{color}")
            el.set("style", ";".join(parts))

    return etree.tostring(root, encoding="utf-8", xml_declaration=True)


def svg_to_png(svg_bytes: bytes, out_png: Path):
    cairosvg.svg2png(bytestring=svg_bytes, write_to=str(out_png))
    print(f"[✓] PNG створено: {out_png}")


# === 🆕 ДОДАНО: малювання тексту на PNG ===
def add_text_to_image(png_path: Path, text: str, font_path: Path, color: str = "#000", size: int = 24, position: str = "bottom"):
    """Додає текст (наприклад дату) до PNG"""
    img = Image.open(png_path)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(str(font_path), size)
    except Exception:
        font = ImageFont.load_default()
        print("[!] Не вдалося завантажити шрифт, використано стандартний.")

    text_w, text_h = draw.textsize(text, font=font)
    margin = 10

    if position == "bottom":
        x = (img.width - text_w) // 2
        y = img.height - text_h - margin
    else:  # top
        x = (img.width - text_w) // 2
        y = margin

    draw.text((x, y), text, font=font, fill=color)
    img.save(png_path)
    print(f"[✓] Текст додано: {text}")


# ---------------------------------------------------------------
if __name__ == "__main__":
    if not INPUT_TEXT.exists() or not SVG_TEMPLATE.exists():
        print("Помилка: відсутній schedule.txt або template.svg")
        exit(1)

    schedule_text = INPUT_TEXT.read_text(encoding="utf-8")
    data = parse_schedule_text(schedule_text)

    all_ids_to_color = set()
    for queue_id, intervals in data.items():
        ids = get_halfhour_ids(queue_id, intervals)
        all_ids_to_color.update(ids)

    svg_bytes = recolor_svg(SVG_TEMPLATE, all_ids_to_color, COLOR_ON, COLOR_OFF)
    OUTPUT_SVG.write_bytes(svg_bytes)
    print(f"[✓] Модифікований SVG збережено: {OUTPUT_SVG}")

    svg_to_png(svg_bytes, OUTPUT_PNG)

    # === Додаємо текст після рендеру ===
    add_text_to_image(OUTPUT_PNG, TEXT, FONT_PATH, TEXT_COLOR, FONT_SIZE, TEXT_POSITION)
