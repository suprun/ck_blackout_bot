#!/bin/bash
# ============================================
# setup_venv.sh — створює та оновлює .venv
# для Raspberry Pi OS (Python 3)
# ============================================

PROJECT_DIR="/home/pi/blackout_bot"
VENV_DIR="$PROJECT_DIR/.venv"
REQ_FILE="$PROJECT_DIR/requirements.txt"

echo "🔍 Перевірка оновлень системи..."
sudo apt update -y >/dev/null

echo "🐍 Перевірка встановлення Python..."
if ! command -v python3 &>/dev/null; then
    echo "➡️  Встановлюємо Python3..."
    sudo apt install python3 -y
fi

echo "📦 Перевірка модуля venv..."
if ! python3 -m venv --help &>/dev/null; then
    echo "➡️  Встановлюємо пакет python3-venv..."
    sudo apt install python3-venv -y
fi

echo "🧱 Створюємо директорію проекту: $PROJECT_DIR"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR" || exit

echo "🧩 Створюємо віртуальне середовище..."
python3 -m venv "$VENV_DIR"

echo "⚙️  Активуємо середовище..."
source "$VENV_DIR/bin/activate"

echo "⬇️  Оновлюємо pip..."
pip install --upgrade pip

if [ -f "$REQ_FILE" ]; then
    echo "📦 Встановлюємо бібліотеки з requirements.txt..."
    pip install -r "$REQ_FILE"
else
    echo "⚠️  Файл requirements.txt не знайдено. Пропускаємо."
fi

echo "✅ Готово! Середовище активоване."
echo "📁 Шлях: $VENV_DIR"
echo "🚀 Приклад запуску:"
echo "   $VENV_DIR/bin/python main.py"
