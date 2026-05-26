import logging
import sqlite3
import requests
from flask import Flask, request, jsonify
import os

TOKEN = "8660161351:AAEGsV68gS860oepV0c1nAxPUkjvBiskWdY" # Токен Главного бота
API_SECRET = "movie_bot_secret_2024_67890" # Пароль для связи с Хелпером
PRIVATE_CHANNEL = -1003800629563 # Твой приватный канал

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# База данных именно Главного бота
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

# ========================================================
# 1. ПРИЕМ ДАННЫХ ОТ ХЕЛПЕРА (По сети, скрытно от юзеров)
# ========================================================
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
        message_id = data.get('message_id')
        
        conn = sqlite3.connect('main_movies.db')
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO movies (code, title, year, description, message_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (code, title, year, description, message_id))
            conn.commit()
            logging.info(f"✅ Фильм '{title}' успешно добавлен в базу Главного бота.")
            conn.close()
            return jsonify({'status': 'success'}), 200
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Code duplicate'}), 400
    except Exception as e:
        logging.error(f"Ошибка в /add_movie: {e}")
        return jsonify({'status': 'error'}), 500

# ========================================================
# 2. ФУНКЦИЯ ГЛАВНОГО БОТА (Общение с обычными людьми)
# ========================================================
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        if not update:
            return 'ok', 200

        # Проверяем, что нам пришло именно текстовое сообщение в чат бота
        if 'message' in update:
            msg = update['message']
            chat_id = msg['chat']['id']
            text = msg.get('text', '').strip()

            if not text:
                return 'ok', 200

            # Команда /start
            if text == '/start':
                send_message(chat_id, "🎬 <b>Добро пожаловать!</b>\n\nОтправьте мне числовой <b>код фильма</b>, и я скину вам ссылку на него!")
                return 'ok', 200

            # Поиск фильма, если пользователь отправил код (цифры)
            if text.isdigit():
                conn = sqlite3.connect('main_movies.db')
                cursor = conn.cursor()
                cursor.execute("SELECT title, year, description, message_id FROM movies WHERE code=?", (text,))
                movie = cursor.fetchone()
                conn.close()

                if movie:
                    m_title, m_year, m_desc, m_msg_id = movie
                    # Очищаем ID канала от "-100" для создания рабочей ссылки
                    clean_id = str(PRIVATE_CHANNEL).replace('-100', '')
                    movie_link = f"https://t.me/c/{clean_id}/{m_msg_id}"
                    
                    send_message(chat_id, 
                        f"🎬 <b>{m_title} ({m_year})</b>\n\n"
                        f"📝 {m_desc}\n\n"
                        f"🍿 <a href='{movie_link}'>СМОТРЕТЬ ФИЛЬМ В КАНАЛЕ</a>")
                else:
                    send_message(chat_id, "❌ Увы, фильм с таким кодом не найден в базе.")
            else:
                send_message(chat_id, "⚠️ Пожалуйста, отправьте корректный числовой код фильма (только цифры).")

        return 'ok', 200
    except Exception as e:
        logging.error(f"Ошибка webhook Главного бота: {e}")
        return 'error', 500

@app.route('/')
def index():
    return "🎬 Главный Бот работает и готов отвечать пользователям!"

# Автоматический сброс и установка вебхука именно для работы с людьми
render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'movie-bot-7qmx.onrender.com')
webhook_url = f"https://{render_host}/{TOKEN}"

try:
    requests.get(f"https://api.telegram.org/bot{TOKEN}/setWebhook", params={"url": webhook_url, "allowed_updates": ["message"]}, timeout=10)
    logging.info(f"✅ Вебхук Главного бота успешно направлен на: {webhook_url}")
except Exception as e:
    logging.error(f"❌ Не удалось обновить вебхук: {e}")

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)