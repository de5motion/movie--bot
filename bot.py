import logging
import sqlite3
import re
import json
import threading
import os
from flask import Flask
import telebot

TOKEN = "8660161351:AAEGsV68gS860oepV0c1nAxPUkjvBiskWdY"
ADMIN_ID = 6777360306  # Твой Telegram ID
PRIVATE_CHANNEL = -1003800629563

# Инициализируем бота и Flask
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Инициализация базы данных SQLite и авто-импорт из JSON
def init_db_and_import():
    conn = sqlite3.connect('main_movies.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            title TEXT,
            year INTEGER,
            description TEXT,
            message_id INTEGER
        )
    ''')
    conn.commit()

    # Автоматическое восстановление из файла movie_backup.json, если он есть рядом
    backup_file = 'movie_backup.json'
    if os.path.exists(backup_file):
        logging.info(f"⏳ Найден файл {backup_file}! Начинаем автоматическое восстановление базы...")
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, list):
                imported_count = 0
                for item in data:
                    code = str(item.get('code') or item.get('id', '')).strip()
                    title = item.get('title') or item.get('name', 'Без названия')
                    year = int(item.get('year', 0))
                    desc = item.get('description', f"Фильм: {title}")
                    msg_id = int(item.get('message_id', 0))
                    
                    if not code:
                        continue
                        
                    try:
                        cursor.execute('''
                            INSERT OR REPLACE INTO movies (code, title, year, description, message_id)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (code, title, year, desc, msg_id))
                        imported_count += 1
                    except Exception as e:
                        logging.error(f"Ошибка импорта фильма {title}: {e}")
                
                conn.commit()
                logging.info(f"✅ УСПЕШНО ВОССТАНОВЛЕНО {imported_count} ФИЛЬМОВ ИЗ JSON-БЭКАПА!")
        except Exception as e:
            logging.error(f"❌ Не удалось прочитать JSON-бэкап: {e}")
    else:
        logging.info("ℹ️ Файл бэкапа movie_backup.json не найден. База запущена пустой.")
        
    conn.close()

# Запускаем создание БД и проверку бэкапа при старте
init_db_and_import()

# === РУЧНАЯ МАССОВАЯ ЗАГРУЗКА СПИСКА ТЕКСТОМ (Если понадобится) ===
@bot.message_handler(func=lambda message: message.text and message.text.startswith('/загрузка') and message.from_user.id == ADMIN_ID)
def handle_bulk_upload(message):
    text = message.text.strip()
    lines = text.split('\n')
    
    conn = sqlite3.connect('main_movies.db')
    cursor = conn.cursor()
    
    added_count = 0
    for line in lines:
        line = line.strip()
        
        if not line or line.startswith('/загрузка') or "Available Movies" in line:
            continue
        
        line = line.lstrip('•').strip()
        
        # Регулярное выражение для очистки значков 🎥 и обработки года/кода
        match = re.search(r'^(.*?)\s*(?:🎥)?\s*\((\d+)\)\s*-\s*(\d+)$', line)
        if match:
            title = match.group(1).strip()
            year = int(match.group(2))
            code = match.group(3).strip()
            
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO movies (code, title, year, description, message_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (code, title, year, f"Фильм: {title}", 0))
                added_count += 1
            except Exception as e:
                logging.error(f"Ошибка вставки строки списка в БД: {e}")
    
    conn.commit()
    conn.close()
    bot.reply_to(message, f"✅ <b>Система восстановления:</b> успешно загружено <b>{added_count}</b> фильмов из текста!")

# === СТАНДАРТНАЯ КОМАНДА /START ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🎬 Добро пожаловать!\n\nВведите числовой <b>код фильма</b>, чтобы получить ссылку.")

# === ПОИСК ПО КОДУ (Для всех пользователей) ===
@bot.message_handler(func=lambda message: message.text and message.text.isdigit())
def search_movie(message):
    code = message.text.strip()
    
    conn = sqlite3.connect('main_movies.db')
    cursor = conn.cursor()
    cursor.execute("SELECT title, year, description, message_id FROM movies WHERE code=?", (code,))
    movie = cursor.fetchone()
    conn.close()

    if movie:
        m_title, m_year, m_desc, m_msg_id = movie
        clean_id = str(PRIVATE_CHANNEL).replace('-100', '')
        
        # Если в базе точный id сообщения равен 0, даем ссылку просто на канал
        if m_msg_id == 0:
            movie_link = f"https://t.me/c/{clean_id}"
        else:
            movie_link = f"https://t.me/c/{clean_id}/{m_msg_id}"
        
        response_text = (
            f"🎬 <b>{m_title} ({m_year if m_year != 0 else 'год не указан'})</b>\n\n"
            f"🍿 <a href='{movie_link}'>СМОТРЕТЬ ФИЛЬМ В КАНАЛЕ</a>"
        )
        bot.reply_to(message, response_text)
    else:
        bot.reply_to(message, "❌ Фильм с таким кодом не найден в базе.")

@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    bot.reply_to(message, "⚠️ Пожалуйста, отправьте корректный числовой код фильма (только цифры).")

# === ЗАГЛУШКА ДЛЯ СЕРВЕРА RENDER (Чтобы не ругался Port Binding) ===
@app.route('/')
def index():
    return "Заглушка порта активна. Бот работает в фоне через Long Polling!", 200

# Функция безопасного запуска Long Polling
def run_bot():
    try:
        # Принудительно очищаем старый вебхук перед переходом на пуллинг
        telebot.TeleBot(TOKEN).delete_webhook()
        logging.info("✅ Старый вебхук удален из системы Telegram.")
        logging.info("🚀 Запуск Infinity Polling...")
        bot.infinity_polling(timeout=20, long_polling_timeout=10)
    except Exception as e:
        logging.error(f"Критическая ошибка пуллинга: {e}")

# === РАЗДЕЛЕНИЕ ПОТОКОВ: БОТ + FLASK ===
if __name__ == "__main__":
    if not os.environ.get("WERKZEUG_RUN_MAIN") and not os.environ.get("GUNICORN_INITIALIZED"):
        os.environ["GUNICORN_INITIALIZED"] = "1"
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        logging.info("🔥 Фоновый поток Long Polling запущен из __main__")
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
else:
    if not os.environ.get("GUNICORN_INITIALIZED"):
        os.environ["GUNICORN_INITIALIZED"] = "1"
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        logging.info("🔥 Фоновый поток Long Polling запущен из-под Gunicorn")
