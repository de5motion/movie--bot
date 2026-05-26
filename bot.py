import logging
import sqlite3
import re
import requests
from flask import Flask, request, jsonify
import os

TOKEN = "8660161351:AAEGsV68gS860oepV0c1nAxPUkjvBiskWdY"
API_SECRET = "movie_bot_secret_2024_67890"
ADMIN_ID = 6777360306  # Твой Telegram ID
PRIVATE_CHANNEL = -1003800629563

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Инициализация базы данных
def init_db():
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
    conn.close()
init_db()

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        logging.error(f"Ошибка отправки сообщения: {e}")

# 1. ПРИЕМ ФИЛЬМОВ ОТ ХЕЛПЕРА (По сети)
@app.route('/add_movie', methods=['POST'])
def add_movie():
    try:
        data = request.get_json()
        if not data or data.get('secret') != API_SECRET:
            return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401
        
        code = data.get('code')
        title = data.get('title')
        year = data.get('year', 0)
        description = data.get('description', '')
        message_id = data.get('message_id', 0)
        
        conn = sqlite3.connect('main_movies.db')
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO movies (code, title, year, description, message_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (code, title, year, description, message_id))
            conn.commit()
            conn.close()
            return jsonify({'status': 'success'}), 200
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Code duplicate'}), 400
    except Exception as e:
        logging.error(f"Ошибка в /add_movie: {e}")
        return jsonify({'status': 'error'}), 500

# 2. ОБРАБОТКА ДЕЙСТВИЙ ПОЛЬЗОВАТЕЛЕЙ И АДМИНА
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        if not update or 'message' not in update:
            return 'ok', 200

        msg = update['message']
        chat_id = msg['chat']['id']
        user_id = msg['from']['id']
        text = msg.get('text', '').strip()

        if not text:
            return 'ok', 200

        # === МАССОВАЯ ЗАГРУЗКА СПИСКА (Только для тебя) ===
        if text.startswith('/загрузка') and user_id == ADMIN_ID:
            lines = text.split('\n')
            
            conn = sqlite3.connect('main_movies.db')
            cursor = conn.cursor()
            
            added_count = 0
            for line in lines:
                line = line.strip()
                
                # Пропускаем команду, пустые строки и заголовки списка
                if not line or line.startswith('/загрузка') or "Available Movies" in line:
                    continue
                
                # Убираем точку списка в начале строки
                line = line.lstrip('•').strip()
                
                # Парсим строки формата: "Название фильма (Год) - Код" или "Название 🎥 (0) - Код"
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
                        logging.error(f"Ошибка вставки в БД: {e}")
            
            conn.commit()
            conn.close()
            send_message(chat_id, f"✅ <b>Система восстановления:</b> успешно загружено <b>{added_count}</b> фильмов!")
            return 'ok', 200

        # === СТАНДАРТНЫЙ ПОИСК ПО КОДУ ===
        if text == '/start':
            send_message(chat_id, "🎬 Добро пожаловать!\n\nВведите числовой <b>код фильма</b>, чтобы получить ссылку.")
            return 'ok', 200

        if text.isdigit():
            conn = sqlite3.connect('main_movies.db')
            cursor = conn.cursor()
            cursor.execute("SELECT title, year, description, message_id FROM movies WHERE code=?", (text,))
            movie = cursor.fetchone()
            conn.close()

            if movie:
                m_title, m_year, m_desc, m_msg_id = movie
                clean_id = str(PRIVATE_CHANNEL).replace('-100', '')
                
                # Если message_id равен 0 (после массовой загрузки), даем общую ссылку на канал
                if m_msg_id == 0:
                    movie_link = f"https://t.me/c/{clean_id}"
                else:
                    movie_link = f"https://t.me/c/{clean_id}/{m_msg_id}"
                
                send_message(chat_id, 
                    f"🎬 <b>{m_title} ({m_year if m_year != 0 else 'год не указан'})</b>\n\n"
                    f"🍿 <a href='{movie_link}'>СМОТРЕТЬ ФИЛЬМ В КАНАЛЕ</a>")
            else:
                send_message(chat_id, "❌ Фильм с таким кодом не найден в базе.")
        else:
            send_message(chat_id, "⚠️ Пожалуйста, отправьте корректный числовой код фильма (только цифры).")

        return 'ok', 200
    except Exception as e:
        logging.error(f"Ошибка в webhook: {e}")
        return 'error', 500

@app.route('/')
def index():
    return "🎬 Главный Бот онлайн и готов к массовому восстановлению!"

# Динамическое обновление вебхука под правильный адрес Render
render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'movie-bot-7-4r18.onrender.com')
webhook_url = f"https://{render_host}/{TOKEN}"

try:
    requests.get(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook", timeout=10)
    requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook", params={"url": webhook_url, "allowed_updates": ["message"]}, timeout=10)
    logging.info(f"✅ Вебхук перенаправлен на: {webhook_url}")
except Exception as e:
    logging.error(f"❌ Вебхук ошибка: {e}")

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 10000))  # Порт 10000 для Render
    app.run(host='0.0.0.0', port=port)