import logging
import sqlite3
from datetime import datetime
import os
import threading
import requests
import telebot
from flask import Flask, request, jsonify

# ===== CONFIGURATION =====
TOKEN = "8616873829:AAF1N_drodK9ugzZ-7XD5sqlPe1DHbQ7bq4"
PRIVATE_CHANNEL = -1003800629563
PUBLIC_CHANNEL = "@englishmoviews"
ADMIN_ID = 6777360306
API_SECRET = "movie_bot_secret_2024_67890"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

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

init_db()

# ===== HELPER FUNCTIONS =====
def check_subscription(user_id):
    try:
        member = bot.get_chat_member(PUBLIC_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

def update_user_stats(user_id, username, first_name):
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users (user_id, username, first_name, requests_count, last_active, total_movies_received)
        VALUES (?, ?, ?, 1, ?, 1)
        ON CONFLICT(user_id) DO UPDATE SET
            requests_count = requests_count + 1,
            last_active = ?,
            total_movies_received = total_movies_received + 1
    ''', (user_id, username, first_name, datetime.now(), datetime.now()))
    conn.commit()
    conn.close()

# ===== TELEGRAM HANDLERS =====
@bot.message_handler(commands=['start'])
def send_welcome(message):
    keyboard = telebot.types.InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        telebot.types.InlineKeyboardButton("🎬 Get Movie", callback_data="get_movie"),
        telebot.types.InlineKeyboardButton("🎥 Movie List", callback_data="movies_list")
    )
    bot.send_message(
        message.chat.id,
        f"🎬 <b>Welcome!</b>\n\nTo get a movie, subscribe to {PUBLIC_CHANNEL} and enter the movie code.",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@bot.message_handler(func=lambda message: message.text and message.text.isdigit())
def handle_movie_code(message):
    code = message.text.strip()
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("SELECT message_id, title, year, description FROM movies WHERE code = ? AND status = 'active'", (code,))
    movie = cursor.fetchone()
    conn.close()

    if not movie:
        bot.reply_to(message, "❌ Code not found.")
        return

    if not check_subscription(message.from_user.id):
        bot.reply_to(message, f"❌ Please subscribe to {PUBLIC_CHANNEL} first!")
        return

    m_id, title, year, desc = movie
    try:
        bot.copy_message(message.chat.id, PRIVATE_CHANNEL, m_id, caption=f"🎬 <b>{title}</b> ({year})", parse_mode="HTML")
        update_user_stats(message.from_user.id, message.from_user.username, message.from_user.first_name)
    except Exception as e:
        bot.reply_to(message, "❌ Error sending movie. Check if message_id is correct.")

# ===== FLASK ROUTES =====
@app.route('/')
def index():
    return "Movie Bot is Live!"

@app.route('/restore', methods=['GET'])
def restore():
    try:
        # Список для восстановления: (код, message_id, название, год)
        # ЗАМЕНИТЕ 0 НА РЕАЛЬНЫЕ ID СООБЩЕНИЙ ИЗ ВАШЕГО КАНАЛА
        movies_list = [
            ("1", 33, "The Revenant", 2015),
            ("2", 20, "Harry Potter 1", 2001),
            ("3", 21, "Harry Potter 2", 2002),
            ("4", 22, "Harry Potter 3", 2004),
            ("5", 27, "Harry Potter 4", 2005),
            ("6", 28, "Harry Potter 5", 2007),
            ("7", 29, "Harry Potter 6", 2009),
            ("8", 30, "Harry Potter 7.1", 2010),
            ("9", 31, "Harry Potter 7.2", 2011),
            ("10", 54, "I Know What You Did Last Summer", 2025),
            ("11", 51, "Jumanji", 2017),
            ("12", 3, "The Black Phone 2", 2025),
            ("13", 43, "Gemini Man", 2019),
            ("14", 40, "Fight Club", 1999),
            ("22", 10, "Sidelined: The QB and Me", 2024),
            ("45", 4, "The Kissing Booth 1", 2018),
            ("56", 2, "After", 2019),
            ("89", 9, "Wyrmwood: Apocalypse", 2021),
            ("100", 19, "Catch Me If You Can", 2002),
            ("101", 42, "Enola Holmes", 2020),
            # Новые фильмы (замените 0 на ID из канала)
            ("475", 0, "THE CONJURING 1", 2009),
            ("320", 0, "THE CONJURING 2", 2008),
            ("456", 0, "THE SOCIAL NETWORK", 0),
            ("400", 0, "JOKER", 0),
            ("574", 0, "KUNG FU PANDA", 0),
            ("335", 0, "WEDNESDAY", 0),
            ("827", 0, "RATATOUILLE", 0),
            ("121", 0, "THE MASK", 0),
            ("629", 0, "BABY DRIVER", 0)
        ]
        
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        for code, m_id, title, year in movies_list:
            cursor.execute('''
                INSERT OR REPLACE INTO movies (code, message_id, title, year, status)
                VALUES (?, ?, ?, ?, 'active')
            ''', (code, m_id, title, year))
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": f"Restored {len(movies_list)} movies"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "movies_list":
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        cursor.execute("SELECT code, title FROM movies WHERE status='active' LIMIT 20")
        rows = cursor.fetchall()
        conn.close()
        text = "🎬 <b>Available:</b>\n" + "\n".join([f"• {r[1]} - <code>{r[0]}</code>" for r in rows])
        bot.send_message(call.message.chat.id, text, parse_mode="HTML")

# ===== RUN =====
def run_bot():
    bot.remove_webhook()
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
