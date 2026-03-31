import logging
import sqlite3
import json
import os
import threading
import requests
import telebot
from datetime import datetime
from flask import Flask, request, jsonify

# ===== CONFIGURATION =====
# Рекомендуется заменить на TOKEN = os.getenv("BOT_TOKEN") для безопасности
TOKEN = "8616873829:AAF1N_drodK9ugzZ-7XD5sqlPe1DHbQ7bq4"
PRIVATE_CHANNEL = -1003800629563
PUBLIC_CHANNEL = "@englishmoviews"
ADMIN_ID = 6777360306

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ===== DATABASE & AUTO-RESTORE =====
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
            status TEXT DEFAULT 'active'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            requests_count INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()
    logging.info("Database initialized.")
    
    # МАЛЕНЬКАЯ ХИТРОСТЬ: Авто-восстановление при запуске
    auto_restore_from_json()

def auto_restore_from_json():
    """Функция читает JSON и наполняет базу данных автоматически"""
    json_path = 'movie_backup.json'
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                movies_list = json.load(f)
            
            conn = sqlite3.connect('movies.db')
            cursor = conn.cursor()
            for m in movies_list:
                cursor.execute('''
                    INSERT OR REPLACE INTO movies (code, message_id, title, year, status)
                    VALUES (?, ?, ?, ?, 'active')
                ''', (str(m['code']), m['message_id'], m['title'], m.get('year', 0)))
            conn.commit()
            conn.close()
            logging.info(f"✅ Auto-restored {len(movies_list)} movies from JSON.")
        except Exception as e:
            logging.error(f"❌ Auto-restore failed: {e}")
    else:
        logging.warning("⚠️ movie_backup.json not found. Skip auto-restore.")

# ===== HELPER FUNCTIONS =====
def check_subscription(user_id):
    try:
        member = bot.get_chat_member(PUBLIC_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

# ===== TELEGRAM HANDLERS =====
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("🎥 Movie List", callback_data="list"))
    bot.send_message(
        message.chat.id, 
        f"🎬 <b>Welcome!</b>\n\nSubscribe to {PUBLIC_CHANNEL} and send me a movie code.",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.message_handler(func=lambda message: message.text and message.text.isdigit())
def handle_code(message):
    code = message.text.strip()
    
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("SELECT message_id, title, year FROM movies WHERE code = ? AND status = 'active'", (code,))
    movie = cursor.fetchone()
    conn.close()

    if not movie:
        bot.reply_to(message, "❌ Code not found.")
        return

    if not check_subscription(message.from_user.id):
        bot.reply_to(message, f"❌ First, subscribe to {PUBLIC_CHANNEL}")
        return

    m_id, title, year = movie
    try:
        # Пересылка видео из приватного канала
        bot.copy_message(
            message.chat.id, 
            from_chat_id=PRIVATE_CHANNEL, 
            message_id=m_id, 
            caption=f"🎬 <b>{title}</b> ({year})\n\nEnjoy watching!",
            parse_mode="HTML"
        )
    except Exception as e:
        bot.reply_to(message, "❌ Error: Video not found in storage or message_id is wrong.")
        logging.error(f"Copy error: {e}")

# ===== FLASK ROUTES =====
@app.route('/')
def index():
    return "Movie Bot is running!"

@app.route('/restore')
def manual_restore():
    auto_restore_from_json()
    return "Restore process triggered."

@bot.callback_query_handler(func=lambda call: call.data == "list")
def show_list(call):
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("SELECT code, title FROM movies WHERE status='active' LIMIT 30")
    rows = cursor.fetchall()
    conn.close()
    
    text = "🎬 <b>Available Movies:</b>\n\n"
    text += "\n".join([f"• <code>{r[0]}</code> - {r[1]}" for r in rows])
    bot.send_message(call.message.chat.id, text, parse_mode="HTML")

# ===== RUNNING =====
def run_bot():
    bot.remove_webhook()
    logging.info("Bot started polling...")
    bot.infinity_polling()

if __name__ == "__main__":
    init_db() # Инициализация + Авто-восстановление
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
