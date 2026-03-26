import logging
import sqlite3
from datetime import datetime
import os
import threading
import time
from flask import Flask, request, jsonify
import requests

# ===== CONFIGURATION =====
TOKEN = "8660161351:AAGdM3sN3Sfi3zd8T0e_AOeFjhwAczQDyHw"
PRIVATE_CHANNEL = -1003800629563
PUBLIC_CHANNEL = "@englishmoviews"
PUBLIC_CHANNEL2 = "@obshaga_life"

# ===== INITIALIZE FLASK =====
app = Flask(__name__)

# ===== LOGGING =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ===== DATABASE =====
_db = None
_db_lock = threading.Lock()

def get_db():
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = sqlite3.connect('movies.db', check_same_thread=False)
                _db.row_factory = sqlite3.Row
    return _db

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movies (
            code TEXT PRIMARY KEY,
            message_id INTEGER,
            title TEXT,
            year INTEGER,
            subtitles_id INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            requests_count INTEGER DEFAULT 0,
            last_active TIMESTAMP
        )
    ''')
    
    cursor.execute("SELECT COUNT(*) FROM movies")
    if cursor.fetchone()[0] == 0:
        movies = [
            ("56", 2, "After", 2019, 12),
            ("12", 3, "The Black Phone 2", 2025, 11),
            ("45", 4, "The Kissing Booth 1", 2018, 0),
            ("22", 10, "Sidelined: The QB and Me", 2024, 13),
            ("89", 9, "Wyrmwood: Apocalypse", 2021, 0),
        ]
        cursor.executemany("INSERT INTO movies VALUES (?, ?, ?, ?, ?)", movies)
    
    conn.commit()
    logging.info("Database initialized")

init_db()

# ===== CACHE =====
_movies_cache = {}
_cache_time = 0

def get_movie_cached(code):
    global _movies_cache, _cache_time
    now = time.time()
    
    if not _movies_cache or (now - _cache_time) > 300:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT code, message_id, title, year, subtitles_id FROM movies")
        rows = cursor.fetchall()
        _movies_cache = {row["code"]: row for row in rows}
        _cache_time = now
    
    return _movies_cache.get(code.upper())

# ===== HELPER FUNCTIONS =====
def send_message(chat_id, text, reply_markup=None):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        return requests.post(url, json=data, timeout=10).json()
    except Exception as e:
        logging.error(f"Error sending message: {e}")
        return None

def send_movie(chat_id, message_id, title, code, year, subtitles_id=None):
    url = f"https://api.telegram.org/bot{TOKEN}/copyMessage"
    
    caption = f"🎬 *{title}* ({year})\n🔑 Code: `{code}`"
    
    if subtitles_id and subtitles_id != 0:
        caption += "\n\n📝 *Subtitles* will be sent after the video.\n"
        caption += "To add: open video → tap '⋮' → 'Add subtitle'"
    
    movie_data = {
        "chat_id": chat_id,
        "from_chat_id": PRIVATE_CHANNEL,
        "message_id": message_id,
        "caption": caption,
        "parse_mode": "Markdown"
    }
    result = requests.post(url, json=movie_data, timeout=15).json()
    
    if subtitles_id and subtitles_id != 0 and result.get("ok"):
        sub_data = {
            "chat_id": chat_id,
            "from_chat_id": PRIVATE_CHANNEL,
            "message_id": subtitles_id,
            "caption": "📝 *Subtitles File*",
            "parse_mode": "Markdown"
        }
        requests.post(url, json=sub_data, timeout=10)
    
    return result

def check_subscription(user_id):
    url = f"https://api.telegram.org/bot{TOKEN}/getChatMember"
    try:
        r1 = requests.get(url, params={"chat_id": PUBLIC_CHANNEL, "user_id": user_id}, timeout=10).json()
        r2 = requests.get(url, params={"chat_id": PUBLIC_CHANNEL2, "user_id": user_id}, timeout=10).json()
        
        sub1 = r1.get("ok") and r1["result"]["status"] in ["member", "administrator", "creator"]
        sub2 = r2.get("ok") and r2["result"]["status"] in ["member", "administrator", "creator"]
        return sub1 and sub2
    except:
        return False

def update_user_stats(user_id, username, first_name):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, first_name, requests_count, last_active)
        VALUES (?, ?, ?, COALESCE((SELECT requests_count + 1 FROM users WHERE user_id = ?), 1), ?)
    ''', (user_id, username, first_name, user_id, datetime.now()))
    conn.commit()

# ===== PROCESS UPDATE =====
def process_update(update):
    try:
        if "message" in update:
            message = update["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            username = message["from"].get("username", "")
            first_name = message["from"].get("first_name", "")
            
            if "text" in message:
                text = message["text"].strip()
                
                if text == "/start":
                    keyboard = {
                        "inline_keyboard": [
                            [{"text": "🎬 Get Movie", "callback_data": "get_movie"}],
                            [{"text": "📊 My Stats", "callback_data": "stats"}],
                            [{"text": "🎥 Movie List", "callback_data": "movies_list"}],
                            [{"text": "ℹ️ Help", "callback_data": "help"}]
                        ]
                    }
                    send_message(
                        chat_id,
                        f"🎬 *Welcome, {first_name}!*\n\n"
                        "🔍 *How to Get a Movie:*\n"
                        "1️⃣ Subscribe to both channels\n"
                        "2️⃣ Enter the movie code\n\n"
                        "👇 *Choose an action:*",
                        keyboard
                    )
                
                else:
                    code = text.upper()
                    movie = get_movie_cached(code)
                    
                    if not check_subscription(user_id):
                        keyboard = {
                            "inline_keyboard": [
                                [{"text": "📢 Subscribe 1", "url": f"https://t.me/{PUBLIC_CHANNEL[1:]}"}],
                                [{"text": "📢 Subscribe 2", "url": f"https://t.me/{PUBLIC_CHANNEL2[1:]}"}]
                            ]
                        }
                        send_message(
                            chat_id,
                            f"❌ *Access Denied!*\n\nSubscribe to:\n{PUBLIC_CHANNEL}\n{PUBLIC_CHANNEL2}",
                            keyboard
                        )
                        return
                    
                    if movie:
                        result = send_movie(
                            chat_id, 
                            movie["message_id"], 
                            movie["title"], 
                            movie["code"], 
                            movie["year"], 
                            movie["subtitles_id"]
                        )
                        if result and result.get("ok"):
                            update_user_stats(user_id, username, first_name)
                            logging.info(f"Movie {code} sent")
                        else:
                            send_message(chat_id, "❌ Error sending movie")
                    else:
                        send_message(chat_id, f"❌ *Invalid Code!*\n\nCode `{code}` not found.\n\nAvailable: 56, 12, 45, 22, 89")
        
        elif "callback_query" in update:
            callback = update["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            data = callback["data"]
            user_id = callback["from"]["id"]
            
            if data == "get_movie":
                send_message(chat_id, "🔍 *Enter movie code*\n\nAvailable: 56, 12, 45, 22, 89")
            
            elif data == "stats":
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT requests_count, last_active FROM users WHERE user_id = ?", (user_id,))
                stats = cursor.fetchone()
                if stats:
                    send_message(chat_id, f"📊 *Your Stats*\n\nMovies: {stats['requests_count']}")
                else:
                    send_message(chat_id, "📭 No stats yet")
            
            elif data == "movies_list":
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("SELECT code, title, year FROM movies ORDER BY code")
                movies = cursor.fetchall()
                if movies:
                    text = "🎬 *Movies:*\n\n"
                    for row in movies:
                        text += f"• {row['title']} ({row['year']}) - `{row['code']}`\n"
                    send_message(chat_id, text)
                else:
                    send_message(chat_id, "📭 No movies")
            
            elif data == "help":
                text = "ℹ️ *Help*\n\n"
                text += "📌 *Codes:*\n"
                text += "• 56 - After (with subtitles)\n"
                text += "• 12 - The Black Phone 2 (with subtitles)\n"
                text += "• 45 - The Kissing Booth 1\n"
                text += "• 22 - Sidelined (with subtitles)\n"
                text += "• 89 - Wyrmwood\n\n"
                text += "📢 *Subscribe to:*\n"
                text += f"{PUBLIC_CHANNEL}\n{PUBLIC_CHANNEL2}"
                send_message(chat_id, text)
    
    except Exception as e:
        logging.error(f"Error: {e}")

# ===== FLASK ROUTES =====
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        if update:
            process_update(update)
        return jsonify({'status': 'ok'})
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/')
def index():
    return "🎬 Movie Bot is running!"

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

# ===== SETUP WEBHOOK =====
def setup_webhook():
    try:
        app_name = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')
        if app_name != 'localhost':
            webhook_url = f"https://{app_name}/{TOKEN}"
            requests.post(f"https://api.telegram.org/bot{TOKEN}/setWebhook", 
                         json={"url": webhook_url}, timeout=10)
            logging.info(f"Webhook set to: {webhook_url}")
    except Exception as e:
        logging.error(f"Webhook error: {e}")

# ===== START =====
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    setup_webhook()
    app.run(host='0.0.0.0', port=port)