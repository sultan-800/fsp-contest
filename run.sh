#!/usr/bin/env bash
# ФСП Контест — быстрый запуск (Linux / macOS)
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
source .venv/bin/activate
pip install -q -r requirements.txt
python manage.py migrate --noinput
python manage.py seed_demo
echo ""
echo "  Откройте http://127.0.0.1:8000"
echo "  Организатор: organizer / Organizer#2026    Спортсмен: ivanov / Athlete#2026"
echo ""
python manage.py runserver 127.0.0.1:8000
