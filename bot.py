import logging
import sqlite3
from datetime import datetime
import os
from flask import Flask, request, jsonify
import requests

# ===== CONFIGURATION =====
TOKEN = "8660161351:AAGdM3sN3Sfi3zd8T0e_AOeFjhwAczQDyHw"
PRIVATE_CHANNEL = -1003800629563
PUBLIC_CHANNEL = "@englishmoviews"

# ===== INITIALIZE FLASK =====
app = Flask(__name__)

# ===== LOGGING =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ===== DATABASE =====
def init_db():
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movies (
            code TEXT PRIMARY KEY,
            message_id INTEGER,
            title TEXT,
            year INTEGER
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
            ("INT001", 2, "Interstellar", 2014),
        ]
        cursor.executemany("INSERT INTO movies VALUES (?, ?, ?, ?)", movies)
    
    conn.commit()
    conn.close()
    logging.info("Database initialized")

# Initialize database
init_db()

# ===== HELPER FUNCTIONS =====
def send_message(chat_id, text, reply_markup=None):
    """Send a message via Telegram API"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        response = requests.post(url, json=data)
        return response.json()
    except Exception as e:
        logging.error(f"Error sending message: {e}")
        return None

def send_movie(chat_id, message_id, title, code, year):
    """Send a movie from private channel"""
    url = f"https://api.telegram.org/bot{TOKEN}/copyMessage"
    data = {
        "chat_id": chat_id,
        "from_chat_id": PRIVATE_CHANNEL,
        "message_id": message_id,
        "caption": f"🎬 *{title}* ({year})\n🔑 Code: `{code}`",
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=data)
        return response.json()
    except Exception as e:
        logging.error(f"Error sending movie: {e}")
        return None

def check_subscription(user_id):
    """Check if user is subscribed"""
    url = f"https://api.telegram.org/bot{TOKEN}/getChatMember"
    data = {
        "chat_id": PUBLIC_CHANNEL,
        "user_id": user_id
    }
    try:
        response = requests.get(url, params=data).json()
        if response["ok"]:
            status = response["result"]["status"]
            return status in ["member", "administrator", "creator"]
        return False
    except Exception as e:
        logging.error(f"Subscription check error: {e}")
        return False

def update_user_stats(user_id, username, first_name):
    """Update user statistics"""
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, first_name, requests_count, last_active)
        VALUES (?, ?, ?, COALESCE((SELECT requests_count + 1 FROM users WHERE user_id = ?), 1), ?)
    ''', (user_id, username, first_name, user_id, datetime.now()))
    conn.commit()
    conn.close()

def get_movie(code):
    """Get movie from database"""
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM movies WHERE code = ?", (code,))
    movie = cursor.fetchone()
    conn.close()
    return movie

def get_all_movies():
    """Get all movies from database"""
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("SELECT code, title, year FROM movies")
    movies = cursor.fetchall()
    conn.close()
    return movies

def get_user_stats(user_id):
    """Get user statistics"""
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("SELECT requests_count, last_active FROM users WHERE user_id = ?", (user_id,))
    stats = cursor.fetchone()
    conn.close()
    return stats

# ===== PROCESS UPDATE =====
def process_update(update):
    """Process a Telegram update"""
    try:
        if "message" in update:
            message = update["message"]
            chat_id = message["chat"]["id"]
            user_id = message["from"]["id"]
            username = message["from"].get("username", "")
            first_name = message["from"].get("first_name", "")
            
            # Check if it's a command
            if "text" in message:
                text = message["text"].strip()
                
                if text == "/start":
                    # Welcome message with inline keyboard
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
                        "📌 *Available Movies:*\n"
                        "• `INT001` - Interstellar\n\n"
                        "🔍 *How to Get a Movie:*\n"
                        "1️⃣ Subscribe to our channel\n"
                        "2️⃣ Enter the movie code\n\n"
                        "👇 *Choose an action:*",
                        keyboard
                    )
                
                elif text.upper().startswith("INT"):
                    # Handle movie code
                    code = text.upper()
                    movie = get_movie(code)
                    
                    if not check_subscription(user_id):
                        keyboard = {
                            "inline_keyboard": [
                                [{"text": "📢 Subscribe", "url": f"https://t.me/{PUBLIC_CHANNEL[1:]}"}]
                            ]
                        }
                        send_message(
                            chat_id,
                            f"❌ *Access Denied!*\n\nPlease subscribe: {PUBLIC_CHANNEL}",
                            keyboard
                        )
                        return
                    
                    if movie:
                        code, message_id, title, year = movie
                        result = send_movie(chat_id, message_id, title, code, year)
                        if result and result.get("ok"):
                            update_user_stats(user_id, username, first_name)
                            logging.info(f"Movie {code} sent to user {user_id}")
                        else:
                            send_message(chat_id, "❌ Error sending movie. Please try again later.")
                    else:
                        send_message(chat_id, f"❌ *Invalid Code!*\n\nCode `{code}` not found.\nAvailable: INT001")
                
                else:
                    send_message(chat_id, "❌ *Invalid command!*\n\nUse /start to see available commands.")
        
        elif "callback_query" in update:
            callback = update["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            message_id = callback["message"]["message_id"]
            data = callback["data"]
            user_id = callback["from"]["id"]
            
            if data == "get_movie":
                send_message(chat_id, "🔍 *Enter movie code*\n\nExample: INT001")
            
            elif data == "stats":
                stats = get_user_stats(user_id)
                if stats:
                    requests_count, last_active = stats
                    text = f"📊 *Your Stats*\n\nMovies received: {requests_count}\nLast active: {last_active[:19] if last_active else 'Never'}"
                else:
                    text = "📭 No statistics yet"
                send_message(chat_id, text)
            
            elif data == "movies_list":
                movies = get_all_movies()
                if movies:
                    text = "🎬 *Available Movies:*\n\n" + "\n".join([f"• {title} ({year}) - `{code}`" for code, title, year in movies])
                else:
                    text = "📭 No movies available"
                send_message(chat_id, text)
            
            elif data == "help":
                text = "ℹ️ *Help*\n\nEnter movie code (INT001) or use /start"
                send_message(chat_id, text)
    
    except Exception as e:
        logging.error(f"Error processing update: {e}")

# ===== FLASK ROUTES =====
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    """Handle Telegram webhook"""
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
    """Home page"""
    return "🎬 Movie Bot is running 24/7!"

@app.route('/health')
def health():
    """Health check"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

# ===== SETUP WEBHOOK =====
def setup_webhook():
    """Set webhook on startup"""
    try:
        app_name = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')
        if app_name != 'localhost':
            webhook_url = f"https://{app_name}/{TOKEN}"
            url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
            response = requests.post(url, json={"url": webhook_url})
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
