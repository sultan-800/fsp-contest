@echo off
chcp 65001 >nul
rem ФСП Контест — быстрый запуск (Windows)
cd /d "%~dp0"
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
python manage.py migrate --noinput
python manage.py seed_demo
echo.
echo   Откройте http://127.0.0.1:8000
echo   Организатор: organizer / Organizer#2026    Спортсмен: ivanov / Athlete#2026
echo.
python manage.py runserver 127.0.0.1:8000
