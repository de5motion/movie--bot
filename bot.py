import logging
import sqlite3
from datetime import datetime
import os
import threading
import time
from flask import Flask, request, jsonify
import requests

# ===== CONFIGURATION =====
TOKEN = "8616873829:AAF0BF9bx4R4wEcMzvhk24zD75Kl82Ieedo"
PRIVATE_CHANNEL = -1003800629563
PUBLIC_CHANNEL = "@englishmoviews"
ADMIN_PASSWORD = "admin123"

# ===== INITIALIZE FLASK =====
app = Flask(__name__)

# ===== LOGGING =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ===== GLOBAL DATABASE CONNECTION =====
_db = None
_db_lock = threading.Lock()

def get_db():
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = sqlite3.connect('movies.db', check_same_thread=False)
                _db.row_factory = sqlite3.Row
                logging.info("Database connection established")
    return _db

# ===== CACHE =====
_movies_cache = {}
_cache_time = 0
_subscription_cache = {}
_subscription_cache_time = {}

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
        logging.info(f"Cache updated with {len(_movies_cache)} movies")
    
    return _movies_cache.get(code.upper())

def check_subscription_cached(user_id):
    global _subscription_cache, _subscription_cache_time
    now = time.time()
    
    if user_id in _subscription_cache:
        if (now - _subscription_cache_time.get(user_id, 0)) < 60:
            return _subscription_cache[user_id]
    
    result = check_subscription_real(user_id)
    _subscription_cache[user_id] = result
    _subscription_cache_time[user_id] = now
    return result

# ===== KEEP-ALIVE =====
def keep_alive():
    while True:
        time.sleep(600)
        try:
            app_name = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')
            if app_name != 'localhost':
                requests.get(f"https://{app_name}/health", timeout=5)
        except:
            pass

threading.Thread(target=keep_alive, daemon=True).start()

# ===== DATABASE INITIALIZATION =====
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
    ("2", 20, "Harry Potter and the Philosopher's Stone", 2001, 0),
    ("3", 21, "Harry Potter and the Chamber of Secrets", 2002, 0),
    ("4", 22, "Harry Potter and the Prisoner of Azkaban", 2004, 0),
    ("5", 27, "Harry Potter and the Goblet of Fire", 2005, 0),
    ("6", 28, "Harry Potter and the Order of the Phoenix", 2007, 0),
    ("7", 29, "Harry Potter and the Half-Blood Prince", 2009, 0),
    ("8", 30, "Harry Potter and the Deathly Hallows - Part 1", 2010, 0),
    ("9", 31, "Harry Potter and the Deathly Hallows - Part 2", 2011, 0),
    ("56", 2, "After", 2019, 12),
    ("12", 3, "The Black Phone 2", 2025, 11),
    ("45", 4, "The Kissing Booth 1", 2018, 0),
    ("22", 10, "Sidelined: The QB and Me", 2024, 13),
    ("89", 9, "Wyrmwood: Apocalypse", 2021, 0),
]
        cursor.executemany("INSERT INTO movies VALUES (?, ?, ?, ?, ?)", movies)
        logging.info("Initial movies added")
    
    conn.commit()
    logging.info("Database initialized")

init_db()

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

def send_movie_fast(chat_id, message_id, title, code, year, subtitles_id=None):
    url = f"https://api.telegram.org/bot{TOKEN}/copyMessage"
    
    subtitles_instruction = (
        "\n\n📝 *How to add subtitles:*\n"
        "1️⃣ Download the .srt file from the next message\n"
        "2️⃣ Open the video in Telegram\n"
        "3️⃣ Tap the '⋮' (three dots) menu\n"
        "4️⃣ Select 'Add subtitle'\n"
        "5️⃣ Choose the downloaded .srt file\n\n"
        "💡 *Alternative:* Use VLC or MX Player"
    )
    
    caption = f"🎬 *{title}* ({year})\n🔑 Code: `{code}`"
    if subtitles_id and subtitles_id != 0:
        caption += subtitles_instruction
    
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
            "caption": "📝 *Subtitles File*\n\nDownload and add to video player.",
            "parse_mode": "Markdown"
        }
        requests.post(url, json=sub_data, timeout=10)
        logging.info(f"Subtitles sent for {code}")
    
    return result

def check_subscription_real(user_id):
    url = f"https://api.telegram.org/bot{TOKEN}/getChatMember"
    try:
        r1 = requests.get(url, params={"chat_id": PUBLIC_CHANNEL, "user_id": user_id}, timeout=10).json()
        sub1 = r1.get("ok") and r1["result"]["status"] in ["member", "administrator", "creator"]
        return sub1
    except Exception as e:
        logging.error(f"Subscription check error: {e}")
        return False

def update_user_stats(user_id, username, first_name):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, first_name, requests_count, last_active)
        VALUES (?, ?, ?, COALESCE((SELECT requests_count + 1 FROM users WHERE user_id = ?), 1), ?)
    ''', (user_id, username, first_name, user_id, datetime.now()))
    conn.commit()

def get_all_movies_cached():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT code, title, year FROM movies ORDER BY code")
    return cursor.fetchall()

def get_user_stats_db(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT requests_count, last_active FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

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
                        "1️⃣ Subscribe to our channel\n"
                        "2️⃣ Enter the movie code\n\n"
                        "👇 *Choose an action:*",
                        keyboard
                    )
                
                else:
                    code = text.upper()
                    movie = get_movie_cached(code)
                    
                    if not check_subscription_cached(user_id):
                        keyboard = {
                            "inline_keyboard": [
                                [{"text": "📢 Subscribe", "url": f"https://t.me/{PUBLIC_CHANNEL[1:]}"}]
                            ]
                        }
                        send_message(
                            chat_id,
                            f"❌ *Access Denied!*\n\nPlease subscribe to:\n{PUBLIC_CHANNEL}\n\nAfter subscribing, try again.",
                            keyboard
                        )
                        return
                    
                    if movie:
                        result = send_movie_fast(
                            chat_id, 
                            movie["message_id"], 
                            movie["title"], 
                            movie["code"], 
                            movie["year"], 
                            movie["subtitles_id"]
                        )
                        if result and result.get("ok"):
                            update_user_stats(user_id, username, first_name)
                            logging.info(f"Movie {code} sent to user {user_id}")
                        else:
                            send_message(chat_id, "❌ Error sending movie. Please try again later.")
                    else:
                        send_message(chat_id, f"❌ *Invalid Code!*\n\nCode `{code}` not found.\n\nAvailable codes: 56, 12, 45, 22, 89")
        
        elif "callback_query" in update:
            callback = update["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            data = callback["data"]
            user_id = callback["from"]["id"]
            
            if data == "get_movie":
                send_message(chat_id, "🔍 *Enter movie code*\n\nAvailable codes: 56, 12, 45, 22, 89")
            
            elif data == "stats":
                stats = get_user_stats_db(user_id)
                if stats:
                    text = f"📊 *Your Stats*\n\nMovies received: {stats['requests_count']}\nLast active: {stats['last_active'][:19] if stats['last_active'] else 'Never'}"
                else:
                    text = "📭 No statistics yet"
                send_message(chat_id, text)
            
            elif data == "movies_list":
                movies = get_all_movies_cached()
                if movies:
                    text = "🎬 *Available Movies:*\n\n"
                    for row in movies:
                        code = row["code"]
                        title = row["title"]
                        year = row["year"]
                        if code in ["56", "12", "22"]:
                            text += f"• {title} ({year}) - `{code}` ✅ (subtitles)\n"
                        else:
                            text += f"• {title} ({year}) - `{code}`\n"
                else:
                    text = "📭 No movies available"
                send_message(chat_id, text)
            
            elif data == "help":
                text = "ℹ️ *Help & Instructions*\n\n"
                text += "📌 *How to get a movie:*\n"
                text += "1️⃣ Subscribe to our channel\n"
                text += "2️⃣ Enter the movie code\n"
                text += "3️⃣ Receive video + subtitles (if available)\n\n"
                text += "🎬 *Available codes:*\n"
                text += "• `56` - After (with subtitles)\n"
                text += "• `12` - The Black Phone 2 (with subtitles)\n"
                text += "• `45` - The Kissing Booth 1\n"
                text += "• `22` - Sidelined: The QB and Me (with subtitles)\n"
                text += "• `89` - Wyrmwood: Apocalypse\n\n"
                text += "📝 *How to add subtitles:*\n"
                text += "1️⃣ Download the .srt file\n"
                text += "2️⃣ Open video → tap '⋮' → 'Add subtitle'\n"
                text += "3️⃣ Select the downloaded file\n\n"
                text += "📢 *Required channel:*\n"
                text += f"• {PUBLIC_CHANNEL}\n\n"
                text += "❓ Need help? Contact channel admins"
                send_message(chat_id, text)
    
    except Exception as e:
        logging.error(f"Error processing update: {e}")

# ===== FLASK ROUTES =====
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        if update:
            logging.info(f"Received update: {update.get('update_id')}")
            process_update(update)
        return jsonify({'status': 'ok'})
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return jsonify({'status': 'error'}), 500

@app.route('/')
def index():
    return "🎬 Movie Bot is running 24/7!"

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

# ===== SETUP WEBHOOK =====
def setup_webhook():
    try:
        app_name = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')
        if app_name != 'localhost':
            webhook_url = f"https://{app_name}/{TOKEN}"
            response = requests.post(f"https://api.telegram.org/bot{TOKEN}/setWebhook", json={"url": webhook_url}, timeout=10)
            if response.json().get("ok"):
                logging.info(f"Webhook set to: {webhook_url}")
            else:
                logging.error(f"Failed to set webhook: {response.text}")
    except Exception as e:
        logging.error(f"Webhook setup error: {e}")

# ===== START =====
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    setup_webhook()
    app.run(host='0.0.0.0', port=port)