import logging
import sqlite3
from datetime import datetime
import os
import threading
import requests
import telebot
from flask import Flask, request, jsonify

# ===== CONFIGURATION =====
TOKEN = "8660161351:AAGdM3sN3Sfi3zd8T0e_AOeFjhwAczQDyHw"
PRIVATE_CHANNEL = -1003800629563
PUBLIC_CHANNEL = "@englishmoviews"
ADMIN_ID = 6777360306
API_SECRET = "movie_bot_secret_2024_67890"

# ===== INITIALIZE =====
bot = telebot.TeleBot(TOKEN)
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
    try:
        member = bot.get_chat_member(PUBLIC_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
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

# ===== TELEGRAM HANDLERS =====
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    
    movies = get_all_movies()
    movie_list = "\n".join([f"• <code>{code}</code> - {title} ({year})" for code, title, year in movies[:5]])
    
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        telebot.types.InlineKeyboardButton("🎬 Get Movie", callback_data="get_movie"),
        telebot.types.InlineKeyboardButton("📊 My Stats", callback_data="stats"),
        telebot.types.InlineKeyboardButton("🎥 Movie List", callback_data="movies_list"),
        telebot.types.InlineKeyboardButton("ℹ️ Help", callback_data="help")
    )
    
    bot.send_message(
        message.chat.id,
        f"🎬 <b>Welcome to Movie Bot, {first_name}!</b>\n\n"
        f"📌 <b>Available Movies:</b>\n{movie_list}\n\n"
        f"🔍 <b>How to get a movie:</b>\n"
        f"1️⃣ Subscribe to {PUBLIC_CHANNEL}\n"
        f"2️⃣ Enter movie code (numeric code)\n\n"
        f"👇 <b>Choose an action:</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@bot.message_handler(func=lambda message: message.text and message.text.isdigit())
def handle_movie_code(message):
    user_id = message.from_user.id
    code = message.text.strip()
    
    movie = get_movie(code)
    
    if not movie:
        bot.reply_to(message, f"❌ <b>Invalid Code!</b>\n\nCode <code>{code}</code> not found.", parse_mode="HTML")
        return
    
    if not check_subscription(user_id):
        keyboard = telebot.types.InlineKeyboardMarkup()
        keyboard.add(
            telebot.types.InlineKeyboardButton("📢 Subscribe", url=f"https://t.me/{PUBLIC_CHANNEL[1:]}"),
            telebot.types.InlineKeyboardButton("✅ Check Subscription", callback_data="check_sub")
        )
        bot.reply_to(
            message,
            f"❌ <b>Access Denied!</b>\n\nPlease subscribe to our channel:\n{PUBLIC_CHANNEL}",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return
    
    code, message_id, title, year, description = movie
    result = send_movie(message.chat.id, message_id, title, code, year, description)
    
    if result and result.get("ok"):
        update_user_stats(user_id, message.from_user.username, message.from_user.first_name)
        bot.send_message(message.chat.id, f"✅ <b>Movie Sent!</b>\n\nEnjoy watching 🎬", parse_mode="HTML")
        logging.info(f"Movie {code} sent to user {user_id}")
    else:
        bot.reply_to(message, "❌ <b>Error!</b>\n\nFailed to send movie. Please try again later.", parse_mode="HTML")

@bot.message_handler(func=lambda message: True)
def handle_unknown(message):
    bot.reply_to(message, "❌ <b>Invalid command!</b>\n\nUse /start to see available commands.", parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data
    
    if data == "get_movie":
        bot.send_message(call.message.chat.id, "🔍 <b>Enter movie code</b>\n\nExample: <code>12345</code>", parse_mode="HTML")
    
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
        bot.send_message(call.message.chat.id, text, parse_mode="HTML")
    
    elif data == "movies_list":
        movies = get_all_movies()
        if movies:
            text = "🎬 <b>Available Movies:</b>\n\n"
            for code, title, year in movies:
                text += f"• <b>{title}</b> ({year}) - <code>{code}</code>\n"
        else:
            text = "📭 No movies available"
        bot.send_message(call.message.chat.id, text, parse_mode="HTML")
    
    elif data == "help":
        movies = get_all_movies()
        text = "ℹ️ <b>Help</b>\n\n"
        text += "🔹 <b>Commands:</b>\n"
        text += "• /start - Main menu\n"
        text += "• Enter numeric code to get movie\n\n"
        text += "🔹 <b>Requirements:</b>\n"
        text += f"• Subscribe to {PUBLIC_CHANNEL}\n\n"
        text += "📌 <b>Available codes:</b>\n"
        for code, title, year in movies[:5]:
            text += f"• <code>{code}</code> - {title}\n"
        bot.send_message(call.message.chat.id, text, parse_mode="HTML")
    
    elif data == "check_sub":
        if check_subscription(user_id):
            bot.send_message(call.message.chat.id, "✅ <b>Subscription confirmed!</b>\n\nYou can now get movies.", parse_mode="HTML")
        else:
            keyboard = telebot.types.InlineKeyboardMarkup()
            keyboard.add(telebot.types.InlineKeyboardButton("📢 Subscribe", url=f"https://t.me/{PUBLIC_CHANNEL[1:]}"))
            bot.send_message(
                call.message.chat.id,
                f"❌ <b>Not subscribed!</b>\n\nPlease subscribe to {PUBLIC_CHANNEL}",
                parse_mode="HTML",
                reply_markup=keyboard
            )
    
    try:
        bot.answer_callback_query(call.id)
    except:
        pass

# ===== API ENDPOINTS =====
@app.route('/add_movie', methods=['POST'])
def add_movie_api():
    """API endpoint to receive movies from helper bot"""
    try:
        data = request.get_json()
        
        if not data or data.get('secret') != API_SECRET:
            logging.warning(f"Unauthorized API access attempt from {request.remote_addr}")
            return jsonify({'error': 'Unauthorized'}), 401
        
        code = data.get('code')
        message_id = data.get('message_id')
        title = data.get('title')
        year = data.get('year')
        description = data.get('description', '')
        
        if not all([code, message_id, title, year]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO movies (code, message_id, title, year, description, status)
            VALUES (?, ?, ?, ?, ?, 'active')
        ''', (code, message_id, title, year, description[:500]))
        
        conn.commit()
        conn.close()
        
        logging.info(f"✅ Movie added via API: {code} - {title}")
        
        try:
            bot.send_message(ADMIN_ID, f"✅ Movie added via API\n\n🎬 {title} ({year})\n🔑 Code: {code}")
        except:
            pass
        
        return jsonify({'status': 'success', 'code': code, 'title': title}), 200
        
    except Exception as e:
        logging.error(f"API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
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

# ===== BOT THREAD FOR GUNICORN =====
def run_bot():
    """Run bot polling in background"""
    try:
        bot.remove_webhook()
        logging.info("Webhook removed, starting polling...")
        bot.infinity_polling(timeout=30, long_polling_timeout=30)
    except Exception as e:
        logging.error(f"Bot polling error: {e}")

# Запускаем бота в фоновом потоке (для gunicorn)
bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()

# Flask-приложение будет запущено gunicorn, НЕ вызываем app.run() вручную
# Для локального запуска оставляем блок if __name__ == "__main__":
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    # Для локальной разработки: запускаем бота и Flask
    run_bot()
    app.run(host='0.0.0.0', port=port, debug=False)