import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
import time
import random
import os
import telebot # Новий імпорт для використання telebot

# --- КОНФІГУРАЦІЯ TELEGRAM BOT API ---
TELEGRAM_BOT_TOKEN = "7854359194:AAFSEIpb5EWKwFEH7sc1U-NDJssWGD8J7IM"

# Ініціалізація об'єкта бота з вашим токеном
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# --- КОНФІГУРАЦІЯ КАНАЛІВ-ДЖЕРЕЛ ---
SOURCE_CHANNELS_CONFIG = [
    {"username": "cherkaskaODA", "is_priority_source": False}, # Основний канал
    {"username": "UkraineAlarmSignal", "is_priority_source": True}, # Канал з тривогами
    {"username": "kpszsu", "is_priority_source": False}, # Змінено з war_monitor
    {"username": "cherkassy_int", "is_priority_source": False} # Новий канал для моніторингу балістики
]

# --- КОНФІГУРАЦІЯ ФІЛЬТРІВ ---
FILTER_HASHTAGS = [
    "#Діалог_влада_бізнес",
    "#Черкащина_територія_співпраці",
    "#Бізнес_платформа_Черкащина",
    "#Черкащина_місце_сили",
    "#Зроблено_в_Україні"
]

# Глобальні фрази-виключення для *будь-якого* вихідного каналу (навіть якщо вони пройшли інші фільтри)
GLOBAL_EXCLUSION_PHRASES = [
    "❗️❗️ПОВІТРЯНА ТРИВОГА",
    "🟢ВІДБІЙ",
    "❗️❗️Відбій повітряної тривоги!"
]

# Фрагменти тексту, які роблять повідомлення "пріоритетним" для каналу області (з cherkaaskaODA)
OBLAST_PRIORITY_PHRASES_CHERKASKAODA = [
    "❗️Підвищена небезпека",
    "❗️", 
    "❗️УВАГА",
    "❗️Підвищена ракетна небезпека"
]

# Фільтри для каналу UkraineAlarmSignal
ALARM_SIGNAL_INCLUDE_PHRASE = "Черкаська обл."
ALARM_SIGNAL_EXCLUDE_SYMBOLS = ["🚨", "🟢"]
ALARM_SIGNAL_TEXT_TO_REPLACE = "(Черкаська обл.)" # Ця константа тепер використовується для заміни на "—"
ALARM_SIGNAL_TEXT_TO_REMOVE_PHRASE_1 = "Перейдіть в укриття!"
ALARM_SIGNAL_TEXT_TO_REMOVE_PHRASE_2 = "Негайно прямуйте в укриття"


# Регулярний вираз для очищення тексту з UkraineAlarmSignal
# Видаляє всі емодзі та вказані фрази
UKRAINE_ALARM_SIGNAL_CLEAN_REGEX = re.compile(
    r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\u200d\ufe0f\u2600-\u26FF\u2700-\u27BF]|\s*' + re.escape(ALARM_SIGNAL_TEXT_TO_REMOVE_PHRASE_1) + r'\s*|\s*' + re.escape(ALARM_SIGNAL_TEXT_TO_REMOVE_PHRASE_2) + r'\s*',
    flags=re.IGNORECASE
)

# Фільтри та повідомлення для каналу kpszsu (замість war_monitor)
MIG_MONITOR_INCLUDE_PHRASE = "Зліт МіГ-31К" # Коректна фраза
MIG_MONITOR_ALERT_MESSAGE = "⚠️ 🛫 Зліт МіГ-31К ВПС рф ⚠️"
KPSZSU_INCLUDE_MISSILE_PHRASE = "Ракетна небезпека" # Нова фраза для kpszsu


# Фільтри та повідомлення для каналу cherkassy_int (балістика)
BALLISTICS_MONITOR_INCLUDE_PHRASE = "Загроза балістики"
# Регулярний вираз для видалення емодзі (включаючи 🔪,➡️,⏺️), "!", "Увага", та символів нового рядка
BALLISTICS_CLEAN_REGEX = re.compile(
    r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\u200d\ufe0f\u2600-\u26FF\u2700-\u27BF🔪➡️⏺️]|\!|Увага|\n',
    flags=re.IGNORECASE
)


# --- КОНФІГУРАЦІЯ КАНАЛІВ ДЛЯ ПУБЛІКАЦІЇ ---
TARGET_CHANNELS_CONFIG = [
    {"name": "Черкаська область", "channel_id": "-1002893004632", "keywords": [], "is_priority_channel": True},
    {"name": "Черкаський район", "channel_id": "-1002661759364", "keywords": ["Черкаський район", " Черкаський", "черкаського", "Черкаси" ,"Сміла", "Смілян", "Городище", "Кам'ян", "Чигирин", "Слобода", "Слобідськ", "Білозір", "Руська Поляна", "Руськополянськ", "Мошн", "Балакле", "Мліїв", "Леськ", "Яснозір", "Дубіїв", "Сагунів", "Хацьк"], "is_priority_channel": False},
    {"name": "Звенигородський район", "channel_id": "-1002727144917", "keywords": ["Звенигородський район", "Звенигород", "звенигород", "Звенигородка", "Ватутін", "Багач", "Шпол", "Тальн", "Лисян", "Катеринопіль", "Вільховець", "Юрків", "Шевченкове", "Моринці"], "is_priority_channel": False},
    {"name": "Золотоніський район", "channel_id": "-1002599334350", "keywords": ["Золотоніський район", "золотоніськ", "золотоніському районі", "Золотонош", "Чорнобай", "Драбів", "Гельмязів", "Вознесенськ", "Піщан", "Шрамків", "Благодатне", "Богодухівка", "Драбове-Барятинське"], "is_priority_channel": False},
    {"name": "Уманський район", "channel_id": "-1002872998914", "keywords": ["Уманський район", " уманськ", "Умань", "Жашків", "Христинів", "Монастирищ", "Mаньків", "Верхнячка", "Цибулів"], "is_priority_channel": False},
]

# --- ФАЙЛИ ІСТОРІЇ ТА СТАНУ ТРИВОГ ---
# Тепер історія буде розділена за джерелами
HISTORY_FILE_PREFIX = "bot_history_" # Префікс для файлів історії (напр., bot_history_cherkaskaODA.json)
ALERT_STATE_FILE = "alert_state.json" 

# --- КОНСТАНТИ ОПТИМІЗАЦІЇ ---
MAX_HISTORY_IDS = 200 # Максимальна кількість записів в published_ids та checked_ids

# --- ІНТЕРВАЛИ ЗАПУСКУ (у секундах) ---
MIN_ALERT_INTERVAL_SEC = 60
MAX_ALERT_INTERVAL_SEC = 120 
MIN_NORMAL_INTERVAL_SEC = 300
MAX_NORMAL_INTERVAL_SEC = 600 
MIN_CYCLE_SLEEP_SEC = 50
MAX_CYCLE_SLEEP_SEC = 90


def load_json_file(filename, default_data):
    """
    Завантажує дані з JSON файлу або повертає default_data, якщо файл не існує/пошкоджений.
    Також конвертує published_ids зі старого формату (список рядків) у новий (список словників).
    """
    data = default_data
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print(f"[ERROR] Помилка читання {filename}. Створюємо новий з даними за замовчуванням.")
                data = default_data
    else:
        print(f"[INFO] Файл {filename} не знайдено. Створюємо новий з даними за замовчуванням.")

    # Перевірка та конвертація published_ids, якщо потрібно (для сумісності зі старими файлами)
    if "published_ids" in data and isinstance(data["published_ids"], list):
        if data["published_ids"] and isinstance(data["published_ids"][0], str):
            print(f"[INFO] Конвертація published_ids у файлі {filename} зі старого формату (список рядків) у новий (список словників).")
            data["published_ids"] = [{"id": item, "text": "", "date": "", "time": ""} for item in data["published_ids"]]
            # Перевіряємо, чи після конвертації розмір не перевищує MAX_HISTORY_IDS
            while len(data["published_ids"]) > MAX_HISTORY_IDS:
                data["published_ids"].pop(0)
    elif "published_ids" not in data:
        data["published_ids"] = [] # Забезпечуємо наявність списку
    
    if "checked_ids" not in data:
        data["checked_ids"] = [] # Забезпечуємо наявність списку

    return data


def save_json_file(filename, data):
    """
    Зберігає дані в JSON файл.
    """
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def get_alert_status():
    """
    Перевіряє alert_state.json та повертає True, якщо є активна тривога, False інакше.
    """
    default_alert_state = {
        "had_connection_issue": False,
        "alerts": {
            "oblast": {"status": False, "start_time": None, "last_sent_image_filename": "0000.png"},
            "raions": {
                "152": {"status": False, "start_time": None},
                "150": {"status": False, "start_time": None},
                "153": {"status": False, "start_time": None},
                "151": {"status": False, "start_time": None}
            },
            "is_first_run_after_load": True
        }
    }
    alert_state = load_json_file(ALERT_STATE_FILE, default_alert_state)

    if alert_state.get('alerts', {}).get('oblast', {}).get('status', False):
        return True

    raions = alert_state.get('alerts', {}).get('raions', {})
    for raion_id in raions:
        if raions[raion_id].get('status', False):
            return True
            
    return False


def send_telegram_request(method, params=None, files=None):
    """
    Надсилає запит до Telegram Bot API.
    Тепер використовує pyTelegramBotAPI (telebot) для відправки повідомлень.
    """
    if method == "sendMessage":
        chat_id = params.get('chat_id')
        text = params.get('text')
        parse_mode = params.get('parse_mode')
        disable_web_page_preview = params.get('disable_web_page_preview', False)
        disable_notification = params.get('disable_notification', False)

        try:
            # telebot.send_message повертає об'єкт Message.
            # Для сумісності з попередньою логікою повертаємо словник з 'ok': True
            sent_message = bot.send_message(
                str(chat_id), # Перетворюємо chat_id на рядок, щоб уникнути помилок типу
                text,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
                disable_notification=disable_notification
            )
            return {'ok': True, 'result': sent_message.json}
        except telebot.apihelper.ApiTelegramException as e:
            # Обробка помилок від Telegram API (наприклад, недійсний chat_id, помилки парсингу)
            print(f"[ERROR] TeleBot API (sendMessage) to chat {chat_id}: {e}")
            return {'ok': False, 'description': str(e)}
        except Exception as e:
            # Загальна обробка інших помилок (наприклад, мережеві проблеми на стороні клієнта)
            print(f"[ERROR] При виконанні запиту до TeleBot API (sendMessage) to chat {chat_id}: {e}")
            return None # Повертаємо None у разі загальної помилки, щоб викликаюча функція знала про збій
    else:
        # Для інших методів API, які не sendMessage, продовжуємо використовувати requests
        # (якщо ви плануєте їх додати в майбутньому)
        api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
        try:
            if files:
                response = requests.post(api_url, data=params, files=files, timeout=10)
            else:
                response = requests.post(api_url, json=params, timeout=10)
                
            response.raise_for_status()
            result = response.json()
            if not result.get('ok'):
                print(f"[ERROR] Telegram API ({method}) to chat {params.get('chat_id', 'N/A')}: {result.get('description', 'Невідома помика')}")
                return None
            return result
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] При виконанні запиту до Telegram API ({method}) to chat {params.get('chat_id', 'N/A')}: {e}")
            return None


def remove_non_printable_chars(text):
    """
    Видаляє з тексту недруковані ASCII-символи та деякі поширені Unicode керуючі символи.
    """
    # Список діапазонів керуючих символів та інших "проблемних" символів
    # \x00-\x1F: ASCII Control characters
    # \x7F: DEL character
    # \x80-\x9F: C1 Control characters (often non-printable)
    # \u00ad: Soft Hyphen (often invisible)
    # \u200b-\u200f: Zero Width Space, Joiner, Non-Joiner, Left-to-Right, Right-to-Left Marks
    # \u202a-\u202e: Bidirectional control characters
    # \u2060-\u206f: Invisible mathematical operators, etc.
    # \ufeff: Byte Order Mark (BOM)
    # \ufff9-\uffff: Special (non-character)
    
    # Видаляємо всі керуючі символи, окрім пробілу (0x20)
    # і залишаємо лише друковані символи Unicode.
    return re.sub(r'[\x00-\x1F\x7F-\x9F\u00AD\u2000-\u200F\u2028-\u202F\u205F\u2060-\u206F\u3000\uFEFF]', '', text)

def add_id_to_history_list(history_list, new_id, max_size):
    """
    Додає новий ID до списку історії, обмежуючи його розмір.
    Видаляє найстаріші записи, якщо розмір перевищує max_size.
    Використовується для списків, що містять лише ID (рядки).
    """
    if new_id not in history_list:
        history_list.append(new_id)
    # Якщо список перевищує максимальний розмір, видаляємо найстаріший елемент
    while len(history_list) > max_size:
        history_list.pop(0) # Видаляємо найстаріший елемент (перший у списку)

def add_published_entry_to_history(history_list, new_entry_dict, max_size):
    """
    Додає новий словник з даними посту до списку опублікованих повідомлень, обмежуючи його розмір.
    Видаляє найстаріші записи, якщо розмір перевищує max_size.
    Використовується для списків, що містять словники.
    """
    new_id = new_entry_dict.get('id')
    if not new_id:
        print("[WARN] Спроба додати запис до історії публікацій без ID. Запис не буде додано.")
        return

    # Перевіряємо, чи ID вже існує у списку словників
    if not any(entry.get('id') == new_id for entry in history_list):
        history_list.append(new_entry_dict)
    
    # Якщо список перевищує максимальний розмір, видаляємо найстаріший елемент
    while len(history_list) > max_size:
        history_list.pop(0) # Видаляємо найстаріший елемент (перший у списку)


def parse_source_channel_for_latest_content(source_username, history):
    """
    Парсить веб-сторінку вказаного каналу та повертає детальний контент
    першого повідомлення, що відповідає глобальним фільтрам і не було раніше перевірено/опубліковано.
    """
    url = f"https://t.me/s/{source_username}"
    print(f"[INFO] Починаємо парсинг сторінки {source_username}: {url}")

    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Помилка при отриманні сторінки {url}: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    channel_history = soup.find('section', class_='tgme_channel_history')

    if not channel_history:
        print(f"[ERROR] Не знайдено секції історії каналу {source_username} на сторінці.")
        return None

    message_elements = channel_history.find_all('div', class_='tgme_widget_message')

    if not message_elements:
        print(f"[INFO] Не знайдено повідомлень на сторінці {source_username}.")
        return None

    for latest_message_div in reversed(message_elements):
        data_post_attr = latest_message_div.get('data-post')
        if not data_post_attr:
            # print("[WARN] Знайдено повідомлення без атрибуту 'data-post'. Пропускаємо.")
            continue

        original_message_id_str = data_post_attr.split('/')[-1]
        unique_post_id = f"{source_username}_{original_message_id_str}" # Унікальний ID для історії
        
        # Оновлена перевірка для published_ids (тепер список словників)
        if any(entry.get('id') == unique_post_id for entry in history["published_ids"]):
            print(f"[DEBUG] Повідомлення ID:{unique_post_id} з {source_username} вже було опубліковано. Пропускаємо.")
            continue
        
        if unique_post_id in history["checked_ids"]: # checked_ids залишається списком рядків
            print(f"[DEBUG] Повідомлення ID:{unique_post_id} з {source_username} вже було перевірено і відхилено. Пропускаємо.")
            continue

        message_info = {
            'original_message_id': original_message_id_str,
            'source_username': source_username, # Додаємо інформацію про джерело
            'unique_post_id': unique_post_id
        }

        date_link_element = latest_message_div.find('a', class_='tgme_widget_message_date')
        if date_link_element:
            message_info['original_link'] = date_link_element.get('href')
            time_element = date_link_element.find('time', class_='time')
            if time_element:
                iso_datetime_str = time_element.get('datetime')
                message_info['original_datetime_iso'] = iso_datetime_str
                if iso_datetime_str:
                    try:
                        dt_object = datetime.fromisoformat(iso_datetime_str.replace('Z', '+00:00'))
                        message_info['original_datetime_parsed'] = dt_object
                    except ValueError:
                        message_info['original_datetime_parsed'] = "Помилка парсингу дати"
                else:
                    message_info['original_datetime_parsed'] = "Атрибут datetime відсутній"
            else:
                message_info['original_link'] = "Посилання не знайдено"
                message_info['original_datetime_parsed'] = "Дата/час не знайдено"

        author_element = latest_message_div.find('div', class_='tgme_widget_message_author')
        if author_element:
            owner_name_element = author_element.find('span', dir="auto")
            if owner_name_element:
                message_info['author'] = owner_name_element.get_text(strip=True)
        else:
            message_info['author'] = "Невідомий автор"

        forwarded_from_element = latest_message_div.find('div', class_='tgme_widget_message_forwarded_from')
        if forwarded_from_element:
            forwarded_name_element = forwarded_from_element.find('span', dir="auto")
            if forwarded_name_element:
                message_info['forwarded_from'] = forwarded_name_element.get_text(strip=True)
        else:
            message_info['forwarded_from'] = None

        text_element = latest_message_div.find('div', class_='tgme_widget_message_text')
        if text_element:
            cleaned_text_html = str(text_element)
            cleaned_text_html = cleaned_text_html.replace('<div class="tgme_widget_message_text js-message_text" dir="auto">', '')
            cleaned_text_html = cleaned_text_html.replace('<span style="display: inline-block; width: 97px;"></span>', '')
            cleaned_text_html = cleaned_text_html.replace('</div>', '')
            
            message_info['text_html'] = cleaned_text_html.strip()
            message_info['text_plain'] = text_element.get_text(separator=' ', strip=True)
            # Видаляємо недруковані символи відразу після отримання тексту
            message_info['text_plain'] = remove_non_printable_chars(message_info['text_plain'])


            links_in_text = [a['href'] for a in text_element.find_all('a', href=True)]
            message_info['links_in_text'] = links_in_text
        else:
            message_info['text_html'] = None
            message_info['text_plain'] = '' # Встановлюємо порожній рядок замість None
            message_info['links_in_text'] = []

        message_info['has_media'] = False
        message_info['media_type'] = None
        message_info['media_url'] = None

        video_tag = latest_message_div.find('video', class_='tgme_widget_message_video')
        if video_tag and video_tag.get('src'):
            message_info['has_media'] = True
            message_info['media_type'] = 'video'
            message_info['media_url'] = video_tag.get('src')
        
        if not message_info['has_media']:
            grouped_photo_wraps = latest_message_div.find_all('a', class_='tgme_widget_message_photo_wrap')
            if grouped_photo_wraps:
                message_info['has_media'] = True
                message_info['media_type'] = 'photos'
                photo_urls = []
                for photo_wrap in grouped_photo_wraps:
                    style_attr = photo_wrap.get('style')
                    if style_attr and 'background-image' in style_attr:
                        start = style_attr.find("url('") + len("url('")
                        end = style_attr.find("')")
                        photo_urls.append(style_attr[start:end])
                if photo_urls:
                    message_info['media_url'] = photo_urls
                
            elif latest_message_div.find('a', class_='tgme_widget_message_photo_wrap'):
                message_info['has_media'] = True
                message_info['media_type'] = 'photo'
                single_photo_wrap = latest_message_div.find('a', class_='tgme_widget_message_photo_wrap')
                style_attr = single_photo_wrap.get('style')
                if style_attr and 'background-image' in style_attr:
                    start = style_attr.find("url('") + len("url('")
                    end = style_attr.find("')")
                    message_info['media_url'] = style_attr[start:end]

        # --- ЗАСТОСУВАННЯ ФІЛЬТРІВ ДЛЯ ДЖЕРЕЛА ---
        if should_process_message_from_source(message_info):
            print(f"[SUCCESS] Повідомлення ID:{message_info['unique_post_id']} з {source_username} пройшло глобальні фільтри джерела.")
            return message_info
        else:
            # Оновлюємо checked_ids з обмеженням
            add_id_to_history_list(history["checked_ids"], unique_post_id, MAX_HISTORY_IDS)
            save_json_file(f"{HISTORY_FILE_PREFIX}{source_username}.json", history)
    
    print(f"[INFO] Не знайдено жодного нового повідомлення з {source_username}, що відповідає критеріям фільтрації.")
    return None


def format_duration(seconds):
    """
    Форматує тривалість в секундах у рядок "Дні:Години:Хвилини:Секунди".
    """
    if seconds is None or not isinstance(seconds, (int, float)):
        return "Н/Д"
    
    seconds = int(seconds)
    
    days = seconds // (24 * 3600)
    seconds %= (24 * 3600)
    
    hours = seconds // 3600
    seconds %= 3600
    
    minutes = seconds // 60
    final_seconds = seconds % 60 # Remaining seconds after minutes

    time_str = f"{hours:02d}:{minutes:02d}:{final_seconds:02d}"
    
    if days > 0:
        return f"{days}д {time_str}"
    else:
        return time_str


def should_process_message_from_source(content):
    """
    Перевіряє, чи відповідає повідомлення загальним критеріям для обробки,
    або специфічним фільтрам для джерела.
    """
    message_id = content.get('unique_post_id', 'N/A')
    text_to_check = content.get('text_plain', '') # Тепер завжди буде рядок завдяки fix в parse_source_channel_for_latest_content
    source_username = content.get('source_username')

    # Глобальні фільтри для всіх джерел
    if content.get('has_media'):
        print(f"  [FILTER] ID:{message_id} - Відхилено: містить медіа ({content.get('media_type')}).")
        return False
    if content.get('forwarded_from'):
        print(f"  [FILTER] ID:{message_id} - Відхилено: переслано від '{content['forwarded_from']}'.")
        return False
    for hashtag in FILTER_HASHTAGS:
        if hashtag.lower() in text_to_check.lower():
            print(f"  [FILTER] ID:{message_id} - Відхилено: містить заборонений хештег '{hashtag}'.")
            return False
    
    # Фільтрація посилань застосовується лише до 'cherkaskaODA'
    if source_username == "cherkaskaODA":
        allowed_link_prefix_oda = f"https://t.me/{source_username}"
        for link in content.get('links_in_text', []):
            # Регістронезалежна перевірка для доменів в посиланнях
            if not (link.lower().startswith(allowed_link_prefix_oda.lower()) or \
                    (link.lower().startswith('https://t.me/') and source_username.lower() in link.lower()) or \
                    (link.lower().startswith('http://t.me/') and source_username.lower() in link.lower())):
                print(f"  [FILTER] ID:{message_id} - Відхилено: містить заборонене посилання '{link}'.")
                return False
    
    for phrase in GLOBAL_EXCLUSION_PHRASES:
        if phrase.lower() in text_to_check.lower():
            print(f"  [FILTER] ID:{message_id} - Відхилено: містить глобальну фразу-виключення '{phrase}'.")
            return False

    # Специфічний фільтр для UkraineAlarmSignal
    if source_username == "UkraineAlarmSignal":
        if ALARM_SIGNAL_INCLUDE_PHRASE.lower() not in text_to_check.lower():
            print(f"  [FILTER] ID:{message_id} - Відхилено з {source_username}: не містить '{ALARM_SIGNAL_INCLUDE_PHRASE}'.")
            return False
        for symbol in ALARM_SIGNAL_EXCLUDE_SYMBOLS:
            if symbol in text_to_check: # Символи регістрозалежні
                print(f"  [FILTER] ID:{message_id} - Відхилено з {source_username}: містить заборонений символ '{symbol}'.")
                return False
        return True

    # Специфічний фільтр для kpszsu (замість war_monitor)
    elif source_username == "kpszsu":
        # Цей канал дозволяє всім повідомленням, що пройшли глобальні фільтри,
        # пройти далі для подальшої обробки в process_and_publish_message_to_channels.
        # Там буде вирішено, чи є це МіГ-31К, чи воно містить ключові слова районів.
        return True

    # Специфічний фільтр для cherkassy_int (Балістика)
    elif source_username == "cherkassy_int":
        if BALLISTICS_MONITOR_INCLUDE_PHRASE.lower() in text_to_check.lower():
            print(f"  [FILTER] ID:{message_id} - Знайдено '{BALLISTICS_MONITOR_INCLUDE_PHRASE}' з {source_username}. Підходить для публікації.")
            return True
        else:
            print(f"  [FILTER] ID:{message_id} - Відхилено з {source_username}: не містить '{BALLISTICS_MONITOR_INCLUDE_PHRASE}'.")
            return False

    # Для інших каналів (наразі тільки cherkaskaODA)
    return True


def post_content_to_telegram(content, history, target_channel_id_to_send, remove_text=None, custom_message_text=None):
    """
    Публікує отриманий контент як нове повідомлення в цільовий канал
    та оновлює історію. Може видаляти певний текст перед публікацією
    або надсилати спеціальний текст замість оригінального.
    """
    if not content:
        print("[ERROR] Немає контенту для публікації.")
        return False

    # Використовуємо custom_message_text, якщо він наданий
    if custom_message_text:
        final_text_to_send = custom_message_text
        parse_mode = None # Для кастомних повідомлень зазвичай plain text
    else:
        # Для UkraineAlarmSignal примусово використовуємо plain text та застосовуємо спеціальне очищення
        if content.get('source_username') == "UkraineAlarmSignal":
            final_text_to_send = content.get('text_plain', '')
            
            # 1. Замінюємо "(Черкаська обл.)" на "—" (регістрочутлива заміна)
            final_text_to_send = final_text_to_send.replace(ALARM_SIGNAL_TEXT_TO_REPLACE, '—')
            
            # 2. Замінюємо "🛸" на "🛩" (регістрочутлива заміна, емодзі)
            final_text_to_send = final_text_to_send.replace("🛸", "🛩")

            # 3. Видаляємо всі інші емодзі та фрази "Перейдіть в укриття!" та "Негайно прямуйте в укриття"
            # Регулярний вираз UKRAINE_ALARM_SIGNAL_CLEAN_REGEX вже має re.IGNORECASE для регістронезалежного видалення фраз
            final_text_to_send = UKRAINE_ALARM_SIGNAL_CLEAN_REGEX.sub('', final_text_to_send).strip()
            
            # 4. Додаткове очищення від зайвих пробілів та порожніх рядків
            final_text_to_send = re.sub(r'\s+', ' ', final_text_to_send).strip()
            final_text_to_send = re.sub(r'\n{2,}', '\n', final_text_to_send).strip()
            parse_mode = None # Завжди plain text для цього джерела

        else: # Для інших джерел зберігаємо попередню логіку HTML/plain text
            message_text = content.get('text_plain', '')
            original_html = content.get('text_html', '')
            parse_mode = "HTML" # Завжди намагаємося використовувати HTML
            
            # Застосовуємо загальне очищення недрукованих символів до plain та html тексту
            # Зауваження: text_plain вже очищений від недрукованих символів в parse_source_channel_for_latest_content
            # original_html також потрібно очистити
            original_html = remove_non_printable_chars(original_html)

            # Якщо потрібно видалити певний текст (застосовується тільки якщо немає custom_message_text)
            if remove_text:
                # Регістрочутлива заміна для remove_text
                message_text = message_text.replace(remove_text, '').strip()
                original_html = original_html.replace(remove_text, '').strip()
                original_html = re.sub(r'(\s*<br\s*/?>\s*){2,}', '<br>', original_html)
                original_html = re.sub(r'\s{2,}', ' ', original_html)

            final_text_to_send = original_html if original_html else message_text
            
            # Перевірка HTML-валідності (базова)
            # Якщо після маніпуляцій текст не виглядає як HTML (наприклад, обрізано теги),
            # або якщо оригінальний HTML був порожнім, перемикаємось на plain text.
            if parse_mode == "HTML" and (not final_text_to_send.strip().startswith('<') or not final_text_to_send.strip().endswith('>')):
                if len(final_text_to_send) != len(original_html) or not original_html.strip():
                    parse_mode = None
    
    if not final_text_to_send:
        print(f"[WARN] Повідомлення ID:{content.get('unique_post_id', 'N/A')} стало порожнім після обробки. Не надсилаємо.")
        return False

    MAX_MESSAGE_LENGTH = 4096
    if len(final_text_to_send) > MAX_MESSAGE_LENGTH:
        print(f"[WARN] Текст повідомлення ID:{content.get('unique_post_id', 'N/A')} занадто довгий для Telegram, буде обрізаний.")
        final_text_to_send = final_text_to_send[:MAX_MESSAGE_LENGTH - 50] + "...\n(Повідомлення було обрізано через великий розмір)"
    
    # !!! ДОДАНО ДЛЯ ДІАГНОСТИКИ !!!
    print(f"[DEBUG_SEND] Attempting to send message {content.get('unique_post_id', 'N/A')} to channel {target_channel_id_to_send}")
    print(f"[DEBUG_SEND] Final text (first 200 chars): '{final_text_to_send[:200]}'")
    print(f"[DEBUG_SEND] Text length: {len(final_text_to_send)}, Parse mode: {parse_mode}")
    # !!! КІНЕЦЬ ДІАГНОСТИКИ !!!

    result = send_telegram_request("sendMessage", {
        "chat_id": target_channel_id_to_send,
        "text": final_text_to_send,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
        "disable_notification": True # Відправляти повідомлення без звукового сповіщення
    })

    if result and result.get('ok'): # Перевіряємо result.get('ok') явно
        unique_id = content.get('unique_post_id')
        history_for_source = load_json_file(f"{HISTORY_FILE_PREFIX}{content['source_username']}.json", {"published_ids": [], "checked_ids": []})
        
        if unique_id:
            # Підготовка даних для нового запису в published_ids
            published_date = ""
            published_time = ""
            original_dt_iso = content.get('original_datetime_iso')
            if original_dt_iso:
                try:
                    dt_obj = datetime.fromisoformat(original_dt_iso.replace('Z', '+00:00'))
                    published_date = dt_obj.strftime("%Y-%m-%d")
                    published_time = dt_obj.strftime("%H:%M:%S")
                except ValueError:
                    pass # У разі помилки парсингу дати/часу залишаємо пусті рядки

            new_published_entry = {
                "id": unique_id,
                "text": final_text_to_send, # Зберігаємо кінцевий текст, який був надісланий
                "date": published_date,
                "time": published_time
            }

            # Використовуємо нову функцію для додавання з обмеженням та розширеними даними
            add_published_entry_to_history(history_for_source["published_ids"], new_published_entry, MAX_HISTORY_IDS)
            save_json_file(f"{HISTORY_FILE_PREFIX}{content['source_username']}.json", history_for_source)
            print(f"[SUCCESS] Повідомлення ID:{unique_id} успішно опубліковано та додано до історії published_ids для {content['source_username']}.")
        else:
            print(f"[WARN] Повідомлення опубліковано, але ID {unique_id} не вдалося додати до історії published_ids або вже існувало для {content['source_username']}.")
        return True
    else:
        # Додаємо більш детальний вивід помилки, якщо result.get('ok') False
        error_description = result.get('description', 'Невідома помилка') if result else "Немає відповіді від API"
        print(f"[ERROR] Не вдалося опублікувати повідомлення {content.get('unique_post_id', 'N/A')} в канал {target_channel_id_to_send}. Причина: {error_description}")
        return False


def process_and_publish_message_to_channels(message_content, history_data_map):
    """
    Обробляє повідомлення, що пройшло глобальні фільтри,
    і публікує його у відповідні канали згідно з їхніми правилами.
    """
    unique_id = message_content.get('unique_post_id')
    text_to_check = message_content.get('text_plain', '')
    source_username = message_content.get('source_username')
    
    published_to_any_channel = False
    
    history_for_source = history_data_map[source_username]

    oblast_channel_config = next((c for c in TARGET_CHANNELS_CONFIG if c.get('is_priority_channel')), None)

    # --- Спеціальна обробка для UkraineAlarmSignal ---
    if source_username == "UkraineAlarmSignal":
        if oblast_channel_config:
            # Видаляємо "(Черкаська обл.)" перед публікацією
            print(f"[PUBLISH_LOGIC] Повідомлення {unique_id} з UkraineAlarmSignal. Публікуємо в '{oblast_channel_config['name']}'.")
            # Зверніть увагу: remove_text тут не передається, оскільки його логіка обробляється всередині post_content_to_telegram
            if post_content_to_telegram(message_content, history_for_source, oblast_channel_config['channel_id']):
                published_to_any_channel = True
        else:
            print(f"[WARN] Пріоритетний канал для області не знайдено, але повідомлення {unique_id} з UkraineAlarmSignal підходить. Публікація не відбулася.")

        # Далі, пропускаємо це ж повідомлення через фільтри районних каналів
        # (якщо воно містить їхні ключові слова)
        print(f"[PUBLISH_LOGIC] Повідомлення {unique_id} з UkraineAlarmSignal. Перевіряємо на відповідність районним каналам.")
        for channel_config in TARGET_CHANNELS_CONFIG:
            if channel_config.get('is_priority_channel'):
                continue # Пропускаємо обласний канал, його вже оброблено

            channel_name = channel_config['name']
            channel_id = channel_config['channel_id']
            channel_keywords = channel_config.get('keywords', [])

            is_suitable_for_district = False
            for keyword in channel_keywords:
                # Регістронезалежна перевірка для ключових слів районів
                if keyword.lower() in text_to_check.lower():
                    is_suitable_for_district = True
                    break
            
            if is_suitable_for_district:
                print(f"[PUBLISH_LOGIC] Повідомлення {unique_id} підходить для '{channel_name}'. Публікуємо.")
                # Зверніть увагу: remove_text тут не передається, оскільки його логіка обробляється всередині post_content_to_telegram
                if post_content_to_telegram(message_content, history_for_source, channel_id):
                    published_to_any_channel = True
        
    # --- Спеціальна обробка для kpszsu (оновлена логіка) ---
    elif source_username == "kpszsu":
        published_to_any_district_channel_from_kpszsu = False # Відстежуємо, чи опубліковано в будь-який районний канал з kpszsu
        
        # 1. Спершу перевіряємо на сповіщення про МіГ-31К (пріоритет)
        if MIG_MONITOR_INCLUDE_PHRASE.lower() in text_to_check.lower():
            print(f"[PUBLISH_LOGIC] Повідомлення {unique_id} з kpszsu містить '{MIG_MONITOR_INCLUDE_PHRASE}'. Надсилаємо загальне сповіщення у всі канали.")
            for channel_config in TARGET_CHANNELS_CONFIG:
                channel_name = channel_config['name']
                channel_id = channel_config['channel_id']
                print(f"[PUBLISH_LOGIC] Надсилання сповіщення МіГ-31К в канал '{channel_name}' ({channel_id}).")
                if post_content_to_telegram(message_content, history_for_source, channel_id, custom_message_text=MIG_MONITOR_ALERT_MESSAGE):
                    published_to_any_channel = True
            # Якщо це МіГ-31К, то подальша районна фільтрація не потрібна.
            # Повідомлення вважається обробленим, і виходимо з функції.
            return

        # 2. Якщо це не сповіщення про МіГ-31К, перевіряємо на відповідність районним ключовим словам
        print(f"[PUBLISH_LOGIC] Повідомлення {unique_id} з kpszsu не є МіГ-331К. Перевіряємо на відповідність районним каналам.")
        
        channels_to_publish_to_kpszsu_districts = [] # Зберігаємо районні канали, що відповідають ключовим словам
        for channel_config in TARGET_CHANNELS_CONFIG:
            # Пропускаємо "Черкаська область" на цьому етапі, її буде оброблено пізніше
            if channel_config.get('is_priority_channel'): 
                continue 

            channel_name = channel_config['name']
            channel_id = channel_config['channel_id']
            channel_keywords = channel_config.get('keywords', [])

            is_suitable_for_district = False
            for keyword in channel_keywords:
                if keyword.lower() in text_to_check.lower():
                    is_suitable_for_district = True
                    break
            
            if is_suitable_for_district:
                channels_to_publish_to_kpszsu_districts.append(channel_config)
                print(f"[PUBLISH_LOGIC] Повідомлення {unique_id} з kpszsu підходить для '{channel_name}'. Додано до списку публікації.")

        # 3. Публікуємо в районні канали, які відповідають ключовим словам
        for channel_config in channels_to_publish_to_kpszsu_districts:
            channel_name = channel_config['name']
            channel_id = channel_config['channel_id']
            print(f"[PUBLISH_LOGIC] Публікуємо повідомлення {unique_id} з kpszsu в районний канал '{channel_name}' ({channel_id}).")
            if post_content_to_telegram(message_content, history_for_source, channel_id):
                published_to_any_channel = True # Загальний прапор будь-якої публікації
                published_to_any_district_channel_from_kpszsu = True # Прапор, що опубліковано в хоча б один районний канал

        # 4. Обробляємо "Черкаська область" канал на основі публікацій в районні канали
        if oblast_channel_config and published_to_any_district_channel_from_kpszsu:
            print(f"[PUBLISH_LOGIC] Повідомлення {unique_id} з kpszsu підходить для публікації в '{oblast_channel_config['name']}' (оскільки опубліковано в районний канал).")
            if post_content_to_telegram(message_content, history_for_source, oblast_channel_config['channel_id']):
                published_to_any_channel = True
        elif oblast_channel_config and not published_to_any_district_channel_from_kpszsu:
            print(f"[PUBLISH_LOGIC] Повідомлення {unique_id} з kpszsu НЕ підходить для публікації в '{oblast_channel_config['name']}' (не опубліковано в жоден районний канал).")

        # 5. Якщо повідомлення з kpszsu не було опубліковано в жоден канал (ні МіГ, ні район), додаємо його до checked_ids.
        # Цей блок спрацює тільки якщо published_to_any_channel все ще False.
        if not published_to_any_channel:
            print(f"[PUBLISH_LOGIC] Повідомлення {unique_id} з kpszsu не підійшло для жодного каналу після детальної фільтрації.")
            add_id_to_history_list(history_for_source["checked_ids"], unique_id, MAX_HISTORY_IDS)
            save_json_file(f"{HISTORY_FILE_PREFIX}{source_username}.json", history_for_source)
            print(f"[INFO] Повідомлення {unique_id} додано до checked_ids для {source_username}.")


    # --- Спеціальна обробка для cherkassy_int (Балістика) ---
    elif source_username == "cherkassy_int":
        # Умова вже регістронезалежна в should_process_message_from_source
        # Якщо повідомлення вже пройшло фільтр should_process_message_from_source (тобто містить "Загроза балістики")
        # формуємо кастомний текст та надсилаємо у ВСІ канали.
        # Важливо: text_to_check вже пройшов remove_non_printable_chars на етапі should_process_message_from_source
        cleaned_ballistics_text = BALLISTICS_CLEAN_REGEX.sub('', text_to_check).strip()
        final_ballistics_alert_message = "🚀 " + cleaned_ballistics_text

        print(f"[PUBLISH_LOGIC] Повідомлення {unique_id} з cherkassy_int містить '{BALLISTICS_MONITOR_INCLUDE_PHRASE}'. Надсилаємо загальне сповіщення про балістику у всі канали: '{final_ballistics_alert_message}'.")
        for channel_config in TARGET_CHANNELS_CONFIG:
            channel_name = channel_config['name']
            channel_id = channel_config['channel_id']
            print(f"[PUBLISH_LOGIC] Надсилання сповіщення про балістику в канал '{channel_name}' ({channel_id}).")
            if post_content_to_telegram(message_content, history_for_source, channel_id, custom_message_text=final_ballistics_alert_message):
                published_to_any_channel = True

    # --- Обробка для cherkaskaODA (існуюча логіка) ---
    elif source_username == "cherkaskaODA":
        is_priority_message_from_oda = False
        for phrase in OBLAST_PRIORITY_PHRASES_CHERKASKAODA:
            # Регістронезалежна перевірка для пріоритетних фраз ODA
            if phrase.lower() in text_to_check.lower():
                is_priority_message_from_oda = True
                break
                
        if oblast_channel_config and is_priority_message_from_oda:
            print(f"[PUBLISH_LOGIC] Повідомлення {unique_id} з cherkaskaODA містить пріоритетну фразу. Публікуємо в '{oblast_channel_config['name']}'.")
            if post_content_to_telegram(message_content, history_for_source, oblast_channel_config['channel_id']):
                published_to_any_channel = True
        elif is_priority_message_from_oda:
            print(f"[WARN] Пріоритетний канал для області не знайдено, але повідомлення {unique_id} з cherkaskaODA містить пріоритетну фразу. Публікація не відбулася.")

        # Перевірка для районних каналів для cherkaskaODA (незалежно від пріоритетності)
        for channel_config in TARGET_CHANNELS_CONFIG:
            if channel_config.get('is_priority_channel'):
                continue

            channel_name = channel_config['name']
            channel_id = channel_config['channel_id']
            channel_keywords = channel_config.get('keywords', [])

            is_suitable_for_district = False
            for keyword in channel_keywords:
                # Регістронезалежна перевірка для ключових слів районів
                if keyword.lower() in text_to_check.lower():
                    is_suitable_for_district = True
                    break
            
            if is_suitable_for_district:
                print(f"[PUBLISH_LOGIC] Повідомлення {unique_id} з cherkaskaODA підходить для '{channel_name}'. Публікуємо.")
                if post_content_to_telegram(message_content, history_for_source, channel_id):
                    published_to_any_channel = True
    else:
        print(f"[WARN] Невідоме джерело '{source_username}' для повідомлення {unique_id}. Пропускаємо обробку.")

    # Цей блок тепер спрацює тільки якщо повідомлення не було опубліковано взагалі
    if not published_to_any_channel:
        print(f"[PUBLISH_LOGIC] Повідомлення {unique_id} не підійшло для жодного каналу після детальної фільтрації.")
        # Якщо повідомлення не було опубліковано в жоден канал, додаємо його до checked_ids.
        # Використовуємо нову функцію для додавання з обмеженням
        add_id_to_history_list(history_for_source["checked_ids"], unique_id, MAX_HISTORY_IDS)
        save_json_file(f"{HISTORY_FILE_PREFIX}{source_username}.json", history_for_source)
        print(f"[INFO] Повідомлення {unique_id} додано до checked_ids для {source_username}.")


# --- ГОЛОВНА ЛОГІКА СКРИПТА (З ЦИКЛОМ ЗАПУСКУ) ---
if __name__ == "__main__":
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Бот запущено.")
    print("----------------------------------------------------------------")

    last_alert_status = get_alert_status() 
    # Нова змінна для відстеження кількості коротких інтервалів після відбою
    post_alert_short_interval_counter = 0

    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [INIT] Початковий стан тривоги: {'Активна' if last_alert_status else 'Неактивна'}.")

    next_full_check_time = time.time() 
    
    while True:
        current_time = time.time()
        
        current_alert_status = get_alert_status()
        
        # Виявлення переходу від тривоги до нормального стану
        if not current_alert_status and last_alert_status:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [TRANSITION] **ПОВІТРЯНУ ТРИВОГУ СКАСОВАНО!** Переходимо до фази {5} коротких інтервалів.")
            post_alert_short_interval_counter = 5 # Встановлюємо лічильник на 5 коротких інтервалів

        # Оновлюємо попередній стан тривоги для наступної ітерації
        last_alert_status = current_alert_status 

        # Визначаємо бажаний інтервал на основі поточного стану
        if current_alert_status:
            current_desired_interval = random.randint(MIN_ALERT_INTERVAL_SEC, MAX_ALERT_INTERVAL_SEC)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ALERT_STATUS] Активна повітряна тривога. Бажаний інтервал повної перевірки: {current_desired_interval} сек.")
            post_alert_short_interval_counter = 0 # Скидаємо лічильник, якщо тривога знову активна
        elif post_alert_short_interval_counter > 0:
            # Використовуємо короткий інтервал, якщо ми в фазі після відбою
            current_desired_interval = random.randint(MIN_ALERT_INTERVAL_SEC, MAX_ALERT_INTERVAL_SEC)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [POST_ALERT] Тривоги немає, виконуємо короткі інтервали ({post_alert_short_interval_counter} залишилось). Бажаний інтервал: {current_desired_interval} сек.")
            post_alert_short_interval_counter -= 1 # Зменшуємо лічильник після використання інтервалу
        else:
            current_desired_interval = random.randint(MIN_NORMAL_INTERVAL_SEC, MAX_NORMAL_INTERVAL_SEC)
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [NORMAL_STATUS] Повітряної тривоги немає. Бажаний інтервал повної перевірки: {current_desired_interval} сек.")

        if current_time >= next_full_check_time:
            print(f"\n--- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
            print("[MAIN_TASK] Настав час для повної перевірки каналів та публікації.")

            # Завантажуємо історію для кожного джерела окремо
            history_data_map = {}
            for source_config in SOURCE_CHANNELS_CONFIG:
                source_username = source_config['username']
                # Переконайтеся, що default_data для published_ids є списком словників
                history_data_map[source_username] = load_json_file(
                    f"{HISTORY_FILE_PREFIX}{source_username}.json",
                    {"published_ids": [], "checked_ids": []}
                )
                print(f"[MAIN_TASK] Історія для {source_username} завантажена.")

            # Обробка кожного каналу-джерела
            for source_config in SOURCE_CHANNELS_CONFIG:
                source_username = source_config['username']
                print(f"[MAIN_TASK] Запуск парсингу каналу @{source_username}...")
                
                latest_processed_post_content = parse_source_channel_for_latest_content(
                    source_username, 
                    history_data_map[source_username]
                )

                if latest_processed_post_content:
                    print(f"[MAIN_TASK] Знайдено повідомлення, що пройшло фільтри джерела {source_username}. Застосовуємо логіку публікації.")
                    process_and_publish_message_to_channels(
                        latest_processed_post_content, 
                        history_data_map
                    )
                else:
                    print(f"[MAIN_TASK] Нових повідомлень, що відповідають критеріям, з {source_username} не знайдено.")
            
            next_full_check_time = current_time + current_desired_interval
            print(f"[MAIN_TASK] Наступна повна перевірка запланована на: {datetime.fromtimestamp(next_full_check_time).strftime('%Y-%m-%d %H:%M:%S')}")
            print("--- Завершено поточний цикл основної задачі ---")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [WAITING] До наступної повної перевірки каналів залишилося приблизно {round(next_full_check_time - current_time, 0)} секунд.")

        sleep_duration = random.randint(MIN_CYCLE_SLEEP_SEC, MAX_CYCLE_SLEEP_SEC)
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [SLEEP] Дрімаємо на {sleep_duration} секунд...")
        time.sleep(sleep_duration)
