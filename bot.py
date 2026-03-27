import logging
import sqlite3
from datetime import datetime
import os
import threading
import requests
import telebot
from flask import Flask, request, jsonify

# ===== CONFIGURATION =====
TOKEN = "8616873829:AAF1N_drodK9ugzZ-7XD5sqlPe1DHbQ7bq4"  # Новый токен основного бота
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
    try:
        member = bot.get_chat_member(PUBLIC_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.error(f"Subscription check error: {e}")
        return False

def update_user_stats(user_id, username, first_name):
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
    if movies:
        movie_list = "\n".join([f"• <code>{code}</code> - {title} ({year})" for code, title, year in movies[:10]])
    else:
        movie_list = "No movies available yet"
    
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
        bot.reply_to(message, f"❌ <b>Invalid Code!</b>\n\nCode <code>{code}</code> not found.\nUse /start to see available codes.", parse_mode="HTML")
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
        bot.send_message(call.message.chat.id, "🔍 <b>Enter movie code</b>\n\nExample: <code>1</code>", parse_mode="HTML")
    
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
        if movies:
            for code, title, year in movies[:5]:
                text += f"• <code>{code}</code> - {title}\n"
        else:
            text += "No movies available yet"
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
        
        code = str(data.get('code'))
        message_id = data.get('message_id')
        title = data.get('title')
        year = data.get('year', 0)
        description = data.get('description', '')
        
        if not all([code, message_id, title]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO movies (code, message_id, title, year, description, status)
            VALUES (?, ?, ?, ?, ?, 'active')
        ''', (code, message_id, title, year if year else 0, description[:500]))
        
        conn.commit()
        conn.close()
        
        logging.info(f"✅ Movie added via API: {code} - {title}")
        
        try:
            bot.send_message(ADMIN_ID, f"✅ Movie added via API\n\n🎬 {title} ({year if year else 'N/A'})\n🔑 Code: {code}")
        except:
            pass
        
        return jsonify({'status': 'success', 'code': code, 'title': title}), 200
        
    except Exception as e:
        logging.error(f"API error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/restore', methods=['GET'])
def restore_movies_endpoint():
    """Restore movies from backup list"""
    try:
        # Список фильмов: (code, message_id, title, year)
        movies_list = [
            ("1", 33, "The Revenant", 2015),
            ("2", 20, "Harry Potter and the Philosopher's Stone", 2001),
            ("3", 21, "Harry Potter and the Chamber of Secrets", 2002),
            ("4", 22, "Harry Potter and the Prisoner of Azkaban", 2004),
            ("5", 27, "Harry Potter and the Goblet of Fire", 2005),
            ("6", 28, "Harry Potter and the Order of the Phoenix", 2007),
            ("7", 29, "Harry Potter and the Half-Blood Prince", 2009),
            ("8", 30, "Harry Potter and the Deathly Hallows - Part 1", 2010),
            ("9", 31, "Harry Potter and the Deathly Hallows - Part 2", 2011),
            ("10", 54, "I Know What You Did Last Summer", 2025),
            ("11", 51, "Jumanji: Welcome to the Jungle", 2017),
            ("12", 3, "The Black Phone 2", 2025),
            ("13", 43, "Gemini Man", 2019),
            ("14", 40, "Fight Club", 1999),
            ("22", 10, "Sidelined: The QB and Me", 2024),
            ("45", 4, "The Kissing Booth 1", 2018),
            ("56", 2, "After", 2019),
            ("89", 9, "Wyrmwood: Apocalypse", 2021),
            ("100", 19, "Catch Me If You Can", 2002),
            ("101", 42, "Enola Holmes", 2020),
        ]
        
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        
        restored = 0
        failed = 0
        
        for code, message_id, title, year in movies_list:
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO movies (code, message_id, title, year, description, status)
                    VALUES (?, ?, ?, ?, ?, 'active')
                ''', (code, message_id, title, year, ''))
                restored += 1
                logging.info(f"Restored: {title} ({year}) - Code: {code}")
            except Exception as e:
                failed += 1
                logging.error(f"Failed to restore {title}: {e}")
        
        conn.commit()
        
        # Проверяем итоговое количество
        cursor.execute("SELECT COUNT(*) FROM movies WHERE status = 'active'")
        total = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'status': 'success',
            'restored': restored,
            'failed': failed,
            'total_movies': total,
            'message': f'Successfully restored {restored} movies. Total active movies: {total}'
        }), 200
        
    except Exception as e:
        logging.error(f"Restore error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/movies/list', methods=['GET'])
def list_movies():
    """Get list of all movies"""
    try:
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        cursor.execute("SELECT code, title, year, status FROM movies ORDER BY year DESC")
        movies = cursor.fetchall()
        conn.close()
        
        movies_list = []
        for code, title, year, status in movies:
            movies_list.append({
                'code': code,
                'title': title,
                'year': year,
                'status': status
            })
        
        return jsonify({
            'status': 'success',
            'count': len(movies_list),
            'movies': movies_list
        }), 200
        
    except Exception as e:
        logging.error(f"List movies error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/')
def index():
    return "🎬 Movie Bot is running 24/7!"

@app.route('/health')
def health():
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

# ===== RUN BOT IN BACKGROUND =====
def run_bot():
    try:
        bot.remove_webhook()
        logging.info("Webhook removed, starting polling...")
        bot.infinity_polling(timeout=30, long_polling_timeout=30)
    except Exception as e:
        logging.error(f"Bot polling error: {e}")

# Запускаем бота в фоне (для gunicorn)
bot_thread = threading.Thread(target=run_bot, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)