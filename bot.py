import logging
import sqlite3
import json
import os
import threading
import requests
import telebot
import base64
from datetime import datetime
from flask import Flask, request, jsonify

# ===== CONFIGURATION =====
TOKEN = "8616873829:AAF1N_drodK9ugzZ-7XD5sqlPe1DHbQ7bq4"
GITHUB_TOKEN = "1003800629563"  # Сюда вставьте НОВЫЙ токен
REPO_NAME = "https://github.com/de5motion/movie--bot"           # Например: "myname/movie-bot"
FILE_PATH = "movie_backup.json"
PRIVATE_CHANNEL = -1003800629563
PUBLIC_CHANNEL = "@englishmoviews"
API_SECRET = "movie_bot_secret_2024_67890"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ===== GITHUB AUTO-UPDATE (СПОСОБ 2) =====
def update_github_backup(new_movie):
    """Добавляет новый фильм прямо в файл на GitHub"""
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

    try:
        # 1. Получаем текущий файл с Гитхаба
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            file_data = res.json()
            sha = file_data['sha']
            content = json.loads(base64.b64decode(file_data['content']).decode('utf-8'))
            
            # 2. Проверяем, нет ли уже такого кода, и добавляем
            if not any(m['code'] == new_movie['code'] for m in content):
                content.append(new_movie)
                
                # 3. Кодируем обратно и отправляем в GitHub
                new_content_b64 = base64.b64encode(json.dumps(content, indent=2, ensure_ascii=False).encode('utf-8')).decode('utf-8')
                payload = {
                    "message": f"🎬 Auto-add: {new_movie['title']}",
                    "content": new_content_b64,
                    "sha": sha
                }
                requests.put(url, json=payload, headers=headers)
                logging.info(f"✅ Фильм {new_movie['title']} сохранен на GitHub навсегда!")
    except Exception as e:
        logging.error(f"❌ Ошибка обновления GitHub: {e}")

# ===== DATABASE LOGIC =====
def init_db():
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS movies (code TEXT PRIMARY KEY, message_id INTEGER, title TEXT, year INTEGER, status TEXT DEFAULT "active")')
    conn.commit()
    conn.close()
    auto_restore()

def auto_restore():
    if os.path.exists(FILE_PATH):
        with open(FILE_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        for m in data:
            cursor.execute("INSERT OR REPLACE INTO movies VALUES (?, ?, ?, ?, 'active')", (str(m['code']), m['message_id'], m['title'], m.get('year', 0)))
        conn.commit()
        conn.close()
        logging.info("🚀 База данных синхронизирована с JSON.")

# ===== API FOR HELPER BOT =====
@app.route('/add_movie', methods=['POST'])
def add_movie():
    data = request.get_json()
    if not data or data.get('secret') != API_SECRET:
        return jsonify({"error": "Unauthorized"}), 401
    
    new_movie = {
        "code": str(data.get('code')),
        "message_id": data.get('message_id'),
        "title": data.get('title'),
        "year": data.get('year', 0)
    }

    # 1. Сначала в локальную базу (чтобы работало сразу)
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO movies VALUES (?, ?, ?, ?, 'active')", (new_movie['code'], new_movie['message_id'], new_movie['title'], new_movie['year']))
    conn.commit()
    conn.close()

    # 2. В фоновом режиме сохраняем на GitHub (чтобы не пропало после перезагрузки)
    threading.Thread(target=update_github_backup, args=(new_movie,)).start()
    
    return jsonify({"status": "success"}), 200

# ===== BOT HANDLERS =====
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🎬 Отправь мне код фильма!")

@bot.message_handler(func=lambda m: m.text.isdigit())
def get_movie(message):
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("SELECT message_id, title, year FROM movies WHERE code=?", (message.text,))
    res = cursor.fetchone()
    conn.close()

    if res:
        bot.copy_message(message.chat.id, PRIVATE_CHANNEL, res[0], caption=f"🎬 {res[1]} ({res[2]})")
    else:
        bot.reply_to(message, "❌ Код не найден.")

# ===== RUN =====
if __name__ == "__main__":
    init_db()
    threading.Thread(target=lambda: bot.infinity_polling(), daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
