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
            try:
                start, end = [t.strip() for t in part.split("-")]
                # Додамо перевірку формату часу
                if not (re.match(r"^\d{1,2}:\d{2}$", start) and re.match(r"^\d{1,2}:\d{2}$", end)):
                    print(f"[!] Пропуск некоректного інтервалу: '{part}' для черги {queue_id}")
                    continue
                intervals.append((start, end))
            except ValueError:
                print(f"[!] Помилка парсингу інтервалу: '{part}' для черги {queue_id}")
                continue
        if intervals:
            result[queue_id] = intervals
    return result


def get_halfhour_ids(queue_id: str, intervals: list) -> list:
    """Перетворює інтервали у список id блоків {queue_id}_{hh}{a|b}"""
    ids = []
    for start, end in intervals:
        try:
            h1, m1 = map(int, start.split(":"))
            h2, m2 = map(int, end.split(":"))
            
            # Обробка 24:00 як кінець дня
            if h2 == 24 and m2 == 00:
                h2 = 23
                m2 = 59 # Включно до кінця 23:59
            
            start_min = h1 * 60 + m1
            end_min = h2 * 60 + m2
            
            # Якщо end_min 00:00 (наступний день), трактуємо як 24:00 поточного
            if end_min == 0 and start_min > 0:
                 end_min = 24 * 60

            # Переконуємось, що час закінчення не раніше часу початку
            if end_min <= start_min:
                # Обробка переходів через північ, наприклад 23:00 - 01:00
                if h2 < h1:
                    end_min = (h2 + 24) * 60 + m2
                elif start_min == end_min and m2 > m1:
                    # Це нормально, наприклад 10:00 - 10:30
                    pass
                else:
                    print(f"[!] Некоректний інтервал (end <= start): {start}-{end} для {queue_id}")
                    continue

            for t in range(start_min, end_min, 30):
                hour = (t // 60) % 24
                half = "a" if (t % 60) < 30 else "b"
                ids.append(f"{queue_id}_{hour:02d}{half}")
                
        except Exception as e:
            print(f"[!] Помилка в get_halfhour_ids для {queue_id} ({start}-{end}): {e}")
            continue
    return ids


def recolor_svg(svg_path: Path, colored_ids: set, color_on: str, color_off: str) -> bytes:
    """
    Фарбує тільки <rect> у шарі Layer_x0020_1:
    • Елементи з id у colored_ids → color_on
    • Інші <rect> з id → color_off
    • Не чіпає фон, рамки, path, текст тощо
    • Працює навіть якщо id мають префікс "_"
    """
    ns = {"svg": "http://www.w3.org/2000/svg"}
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(svg_path), parser)
    root = tree.getroot()

    # Обидва варіанти ID: "1.1_00a" і "_1.1_00a"
    wanted = set()
    for _id in colored_ids:
        wanted.add(_id)
        wanted.add(f"_{_id}")

    # Шукаємо основний шар (CorelDRAW)
    layer = root.xpath(".//svg:g[@id='Layer_x0020_1']", namespaces=ns)
    scope = layer[0] if layer else root

    # Беремо тільки прямокутники, які мають id
    rects = scope.xpath(".//svg:rect[@id]", namespaces=ns)

    count_total, count_on = 0, 0
    for el in rects:
        el_id = el.get("id")
        if not el_id:
            continue
        count_total += 1

        target_color = color_on if el_id in wanted else color_off

        # inline fill перекриває класи CorelDRAW (.fil*)
        el.set("fill", target_color)
        style = el.get("style") or ""
        parts = [p for p in style.split(";") if p.strip() and not p.strip().startswith("fill:")]
        parts.append(f"fill:{target_color}")
        el.set("style", ";".join(parts))

        if el_id in wanted:
            count_on += 1

    print(f"[✓] Прямокутників знайдено: {count_total}, пофарбовано: {count_on}")
    return etree.tostring(root, encoding="utf-8", xml_declaration=True)


def svg_to_png(svg_bytes: bytes, out_png: Path):
    if not svg_bytes:
        print("[!] SVG байти порожні, конвертація в PNG скасована.")
        return
    try:
        cairosvg.svg2png(bytestring=svg_bytes, write_to=str(out_png))
        print(f"[✓] PNG створено: {out_png}")
    except Exception as e:
        print(f"[!] Помилка конвертації SVG в PNG (cairosvg): {e}")


# === 🆕 ВИПРАВЛЕНО: малювання тексту на PNG ===
def add_text_to_image(png_path: Path, text: str, font_path: Path, color: str = "#000", size: int = 24, position: str = "bottom"):
    """Додає текст (наприклад дату) до PNG"""
    if not png_path.exists():
        print(f"[!] Помилка: PNG файл {png_path} не знайдено для додавання тексту.")
        return
        
    try:
        img = Image.open(png_path)
        draw = ImageDraw.Draw(img)
    except Exception as e:
        print(f"[!] Помилка відкриття PNG: {e}")
        return

    try:
        font = ImageFont.truetype(str(font_path), size)
    except Exception:
        print("[!] Не вдалося завантажити шрифт, використано стандартний.")
        font = ImageFont.load_default()

    # --- ВИПРАВЛЕНО ---
    # `draw.textsize()` було видалено в Pillow 10.0.0
    # Використовуємо font.getlength() для ширини
    try:
        text_w = font.getlength(text)
    except Exception:
         # Фоллбек для старих версій Pillow або несподіваних помилок
         text_w = len(text) * (size // 2)

    # Використовуємо font.getbbox() для отримання точних меж тексту (left, top, right, bottom)
    # Це потрібно для коректного вертикального вирівнювання
    try:
        # getbbox може кинути помилку для порожніх рядків
        if not text:
            raise ValueError("Text is empty")
        left, top, right, bottom = font.getbbox(text)
    except (ValueError, AttributeError):
        print("[!] Не вдалося отримати межі тексту (можливо, текст порожній).")
        left, top, right, bottom = (0, 0, 0, size) # Припускаємо висоту = розміру шрифту
    # --- КІНЕЦЬ ВИПРАВЛЕННЯ ---

    margin = 10

    if position == "bottom":
        # Горизонтальне центрування
        x = (img.width - text_w) // 2
        # --- ВИПРАВЛЕНО ---
        # Вертикальне вирівнювання: від нижнього краю віднімаємо 'margin' 
        # і висоту тексту ('bottom' з bbox)
        y = img.height - bottom - margin
        # --- КІНЕЦЬ ВИПРАВЛЕННЯ ---
    else:  # top
        # Горизонтальне центрування
        x = (img.width - text_w) // 2
        # --- ВИПРАВЛЕНО ---
        # Вертикальне вирівнювання: 'margin' мінус 'top' з bbox 
        # (оскільки 'top' може бути негативним)
        y = margin - top
        # --- КІНЕЦЬ ВИПРАВЛЕННЯ ---

    draw.text((x, y), text, font=font, fill=color)
    
    try:
        img.save(png_path)
        print(f"[✓] Текст додано: {text}")
    except Exception as e:
        print(f"[!] Помилка збереження PNG з текстом: {e}")


# ---------------------------------------------------------------
if __name__ == "__main__":
    if not INPUT_TEXT.exists():
        print(f"Помилка: відсутній файл розкладу: {INPUT_TEXT}")
        exit(1)
    if not SVG_TEMPLATE.exists():
        print(f"Помилка: відсутній файл шаблону: {SVG_TEMPLATE}")
        exit(1)
    if not FONT_PATH.exists() and TEXT:
         print(f"[!] Увага: файл шрифту {FONT_PATH} не знайдено. Буде використано стандартний.")

    schedule_text = INPUT_TEXT.read_text(encoding="utf-8")
    data = parse_schedule_text(schedule_text)
    if not data:
        print("[!] Розклад порожній або не вдалося розпарсити.")
        # Все одно генеруємо картинку (всі будуть OFF)
        # exit(1)

    all_ids_to_color = set()
    for queue_id, intervals in data.items():
        ids = get_halfhour_ids(queue_id, intervals)
        all_ids_to_color.update(ids)
    
    if data:
        print(f"[i] З розкладу отримано {len(all_ids_to_color)} ID півгодинних блоків.")

    svg_bytes = recolor_svg(SVG_TEMPLATE, all_ids_to_color, COLOR_ON, COLOR_OFF)
    
    if not svg_bytes:
        print("[!] Не вдалося згенерувати SVG. Вихід.")
        exit(1)
        
    OUTPUT_SVG.write_bytes(svg_bytes)
    print(f"[✓] Модифікований SVG збережено: {OUTPUT_SVG}")

    svg_to_png(svg_bytes, OUTPUT_PNG)

    # === Додаємо текст після рендеру ===
    if TEXT:
        add_text_to_image(OUTPUT_PNG, TEXT, FONT_PATH, TEXT_COLOR, FONT_SIZE, TEXT_POSITION)
    else:
        print("[i] Текст для додавання порожній, пропуск.")
