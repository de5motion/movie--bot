import logging
import sqlite3
from datetime import datetime
import os
from flask import Flask, request, jsonify
import requests
import re

# ===== CONFIGURATION =====
TOKEN = "8660161351:AAGdM3sN3Sfi3zd8T0e_AOeFjhwAczQDyHw"
PRIVATE_CHANNEL = -1003800629563
PUBLIC_CHANNEL = "@englishmoviews"
ADMIN_ID = 6777360306  # Your Telegram ID

# ===== API CONFIGURATION FOR MAIN BOT =====
API_SECRET = "movie_bot_secret_2024_67890"  # Secret key for API calls

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
            year INTEGER,
            description TEXT,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active'
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            requests_count INTEGER DEFAULT 0,
            last_active TIMESTAMP,
            total_movies_received INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    conn.close()
    logging.info("Database initialized")

init_db()

# ===== HELPER FUNCTIONS =====
def send_message(chat_id, text, reply_markup=None):
    """Send a message via Telegram API"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        data["reply_markup"] = reply_markup
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.json()
    except Exception as e:
        logging.error(f"Error sending message: {e}")
        return None

def send_movie(chat_id, message_id, title, code, year, description=""):
    """Send a movie from private channel"""
    url = f"https://api.telegram.org/bot{TOKEN}/copyMessage"
    
    caption = f"🎬 <b>{title}</b> ({year})\n🔑 Code: <code>{code}</code>"
    if description:
        caption += f"\n📝 {description[:200]}"
    
    data = {
        "chat_id": chat_id,
        "from_chat_id": PRIVATE_CHANNEL,
        "message_id": message_id,
        "caption": caption,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=data, timeout=15)
        return response.json()
    except Exception as e:
        logging.error(f"Error sending movie: {e}")
        return None

def check_subscription(user_id):
    """Check if user is subscribed"""
    url = f"https://api.telegram.org/bot{TOKEN}/getChatMember"
    params = {
        "chat_id": PUBLIC_CHANNEL,
        "user_id": user_id
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        result = response.json()
        if result.get("ok"):
            status = result["result"]["status"]
            return status in ["member", "administrator", "creator"]
        return False
    except Exception as e:
        logging.error(f"Subscription check error: {e}")
        return False

def update_user_stats(user_id, username, first_name):
    """Update user statistics"""
    try:
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, requests_count, last_active, total_movies_received)
            VALUES (?, ?, ?, 1, ?, 1)
            ON CONFLICT(user_id) DO UPDATE SET
                requests_count = requests_count + 1,
                last_active = ?,
                total_movies_received = total_movies_received + 1,
                username = COALESCE(?, username),
                first_name = COALESCE(?, first_name)
        ''', (user_id, username, first_name, datetime.now(), datetime.now(), username, first_name))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"Error updating user stats: {e}")
        return False

def get_movie(code):
    """Get movie from database"""
    try:
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        cursor.execute("SELECT code, message_id, title, year, description FROM movies WHERE code = ? AND status = 'active'", (code,))
        movie = cursor.fetchone()
        conn.close()
        return movie
    except Exception as e:
        logging.error(f"Error getting movie: {e}")
        return None

def get_all_movies():
    """Get all movies from database"""
    try:
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        cursor.execute("SELECT code, title, year FROM movies WHERE status = 'active' ORDER BY year DESC")
        movies = cursor.fetchall()
        conn.close()
        return movies
    except Exception as e:
        logging.error(f"Error getting movies: {e}")
        return []

def get_user_stats(user_id):
    """Get user statistics"""
    try:
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        cursor.execute("SELECT requests_count, last_active, total_movies_received FROM users WHERE user_id = ?", (user_id,))
        stats = cursor.fetchone()
        conn.close()
        return stats
    except Exception as e:
        logging.error(f"Error getting user stats: {e}")
        return None

# ===== API ENDPOINT FOR HELPER BOT =====
@app.route('/add_movie', methods=['POST'])
def add_movie_api():
    """API endpoint to receive movies from helper bot"""
    try:
        # Get data
        data = request.get_json()
        
        # Verify secret key
        if not data or data.get('secret') != API_SECRET:
            logging.warning(f"Unauthorized API access attempt from {request.remote_addr}")
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Extract movie data
        code = data.get('code')
        message_id = data.get('message_id')
        title = data.get('title')
        year = data.get('year')
        description = data.get('description', '')
        
        # Validate required fields
        if not all([code, message_id, title, year]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Add to main bot's database
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        
        # Insert or replace movie
        cursor.execute('''
            INSERT OR REPLACE INTO movies (code, message_id, title, year, description, status)
            VALUES (?, ?, ?, ?, ?, 'active')
        ''', (code, message_id, title, year, description[:500]))
        
        conn.commit()
        conn.close()
        
        logging.info(f"✅ Movie added via API: {code} - {title}")
        
        # Send notification to admin
        try:
            send_message(ADMIN_ID, f"✅ Movie added via API\n\n🎬 {title} ({year})\n🔑 Code: {code}\n🆔 Msg ID: {message_id}")
        except:
            pass
        
        return jsonify({'status': 'success', 'code': code, 'title': title}), 200
        
    except Exception as e:
        logging.error(f"API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health', methods=['GET'])
def api_health():
    """API health check"""
    try:
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM movies WHERE status = 'active'")
        movie_count = cursor.fetchone()[0]
        conn.close()
        
        return jsonify({
            'status': 'healthy',
            'movies_count': movie_count,
            'api_secret_configured': True
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

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
            
            if "text" in message:
                text = message["text"].strip()
                
                if text == "/start":
                    movies = get_all_movies()
                    movie_list = "\n".join([f"• <code>{code}</code> - {title} ({year})" for code, title, year in movies[:5]])
                    
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
                        f"🎬 <b>Welcome to Movie Bot, {first_name}!</b>\n\n"
                        f"📌 <b>Available Movies:</b>\n{movie_list}\n\n"
                        f"🔍 <b>How to get a movie:</b>\n"
                        f"1️⃣ Subscribe to {PUBLIC_CHANNEL}\n"
                        f"2️⃣ Enter movie code (numeric code)\n\n"
                        f"👇 <b>Choose an action:</b>",
                        keyboard
                    )
                
                elif text.isdigit():  # Numeric code
                    code = text
                    movie = get_movie(code)
                    
                    if not movie:
                        send_message(chat_id, f"❌ <b>Invalid Code!</b>\n\nCode <code>{code}</code> not found.\nUse /start to see available movies.")
                        return
                    
                    if not check_subscription(user_id):
                        keyboard = {
                            "inline_keyboard": [
                                [{"text": "📢 Subscribe", "url": f"https://t.me/{PUBLIC_CHANNEL[1:]}"}],
                                [{"text": "✅ Check Subscription", "callback_data": "check_sub"}]
                            ]
                        }
                        send_message(
                            chat_id,
                            f"❌ <b>Access Denied!</b>\n\nPlease subscribe to our channel:\n{PUBLIC_CHANNEL}",
                            keyboard
                        )
                        return
                    
                    code, message_id, title, year, description = movie
                    result = send_movie(chat_id, message_id, title, code, year, description)
                    
                    if result and result.get("ok"):
                        update_user_stats(user_id, username, first_name)
                        send_message(chat_id, f"✅ <b>Movie Sent!</b>\n\nEnjoy watching 🎬")
                        logging.info(f"Movie {code} sent to user {user_id}")
                    else:
                        send_message(chat_id, "❌ <b>Error!</b>\n\nFailed to send movie. Please try again later.")
                
                else:
                    send_message(chat_id, "❌ <b>Invalid command!</b>\n\nUse /start to see available commands.")
        
        elif "callback_query" in update:
            callback = update["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            data = callback["data"]
            user_id = callback["from"]["id"]
            
            try:
                url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
                requests.post(url, json={"callback_query_id": callback["id"]})
            except:
                pass
            
            if data == "get_movie":
                send_message(chat_id, "🔍 <b>Enter movie code</b>\n\nExample: <code>12345</code>")
            
            elif data == "stats":
                stats = get_user_stats(user_id)
                if stats:
                    requests_count, last_active, total_movies = stats
                    text = f"📊 <b>Your Stats</b>\n\n"
                    text += f"📝 Requests: {requests_count}\n"
                    text += f"🎬 Movies Received: {total_movies}\n"
                    text += f"🕐 Last Active: {last_active[:19] if last_active else 'Never'}"
                else:
                    text = "📭 No statistics yet"
                send_message(chat_id, text)
            
            elif data == "movies_list":
                movies = get_all_movies()
                if movies:
                    text = "🎬 <b>Available Movies:</b>\n\n"
                    for code, title, year in movies:
                        text += f"• <b>{title}</b> ({year}) - <code>{code}</code>\n"
                else:
                    text = "📭 No movies available"
                send_message(chat_id, text)
            
            elif data == "help":
                text = "ℹ️ <b>Help</b>\n\n"
                text += "🔹 <b>Commands:</b>\n"
                text += "• /start - Main menu\n"
                text += "• Enter numeric code to get movie\n\n"
                text += "🔹 <b>Requirements:</b>\n"
                text += f"• Subscribe to {PUBLIC_CHANNEL}\n\n"
                text += "📌 <b>Available codes:</b>\n"
                movies = get_all_movies()
                for code, title, year in movies[:5]:
                    text += f"• <code>{code}</code> - {title}\n"
                send_message(chat_id, text)
            
            elif data == "check_sub":
                if check_subscription(user_id):
                    send_message(chat_id, "✅ <b>Subscription confirmed!</b>\n\nYou can now get movies.")
                else:
                    keyboard = {
                        "inline_keyboard": [
                            [{"text": "📢 Subscribe", "url": f"https://t.me/{PUBLIC_CHANNEL[1:]}"}]
                        ]
                    }
                    send_message(chat_id, "❌ <b>Not subscribed!</b>\n\nPlease subscribe to the channel:", keyboard)
    
    except Exception as e:
        logging.error(f"Error processing update: {e}")
        import traceback
        logging.error(traceback.format_exc())

# ===== FLASK ROUTES =====
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    """Handle Telegram webhook"""
    try:
        update = request.get_json()
        if update:
            logging.info(f"Received update")
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
    try:
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM movies WHERE status='active'")
        movie_count = cursor.fetchone()[0]
        conn.close()
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'movies_count': movie_count
        })
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

# ===== SETUP WEBHOOK =====
def setup_webhook():
    """Set webhook on startup"""
    try:
        app_name = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
        if app_name and app_name != 'localhost':
            webhook_url = f"https://{app_name}/{TOKEN}"
            url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
            response = requests.post(url, json={"url": webhook_url}, timeout=10)
            if response.json().get("ok"):
                logging.info(f"✅ Webhook set to: {webhook_url}")
            else:
                logging.error(f"❌ Failed to set webhook")
    except Exception as e:
        logging.error(f"Webhook setup error: {e}")

# ===== START =====
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    setup_webhook()
    app.run(host='0.0.0.0', port=port, debug=False)