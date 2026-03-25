import logging
import sqlite3
from datetime import datetime
import os
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# ===== CONFIGURATION =====
TOKEN = "8660161351:AAGdM3sN3Sfi3zd8T0e_AOeFjhwAczQDyHw"
PRIVATE_CHANNEL = -1003800629563
PUBLIC_CHANNEL = "@englishmoviews"

# ===== INITIALIZE =====
app = Flask(__name__)
application = Application.builder().token(TOKEN).build()

# ===== LOGGING =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ===== DATABASE =====
def init_db():
    """Initialize database"""
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
        logging.info("Initial movies added")
    
    conn.commit()
    conn.close()
    logging.info("Database initialized")

# ===== SUBSCRIPTION CHECK =====
async def is_subscribed(user_id, bot):
    """Check if user is subscribed"""
    try:
        member = await bot.get_chat_member(chat_id=PUBLIC_CHANNEL, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.error(f"Subscription error: {e}")
        return False

# ===== COMMAND /START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message"""
    user = update.effective_user
    
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, username, first_name, last_active)
        VALUES (?, ?, ?, ?)
    ''', (user.id, user.username, user.first_name, datetime.now()))
    conn.commit()
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("🎬 Get Movie", callback_data="get_movie")],
        [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
        [InlineKeyboardButton("🎥 Movie List", callback_data="movies_list")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🎬 *Welcome, {user.first_name}!*\n\n"
        "📌 *Available Movies:*\n"
        "• `INT001` - Interstellar\n\n"
        "🔍 *How to Get a Movie:*\n"
        "1️⃣ Subscribe to our channel\n"
        "2️⃣ Enter the movie code\n\n"
        "👇 *Choose an action:*",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# ===== HANDLE MOVIE CODE =====
async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send movie by code"""
    user_id = update.effective_user.id
    text = update.message.text.strip().upper()
    
    if not await is_subscribed(user_id, context.bot):
        keyboard = [[InlineKeyboardButton("📢 Subscribe", url=f"https://t.me/{PUBLIC_CHANNEL[1:]}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"❌ *Access Denied!*\n\nPlease subscribe: {PUBLIC_CHANNEL}",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        return
    
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM movies WHERE code = ?", (text,))
    movie = cursor.fetchone()
    
    if movie:
        code, message_id, title, year = movie
        try:
            await context.bot.copy_message(
                chat_id=update.effective_chat.id,
                from_chat_id=PRIVATE_CHANNEL,
                message_id=message_id,
                caption=f"🎬 *{title}* ({year})\n🔑 Code: `{code}`",
                parse_mode='Markdown'
            )
            cursor.execute('''
                UPDATE users SET requests_count = requests_count + 1, last_active = ?
                WHERE user_id = ?
            ''', (datetime.now(), user_id))
            conn.commit()
            logging.info(f"Movie {code} sent to user {user_id}")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
    else:
        await update.message.reply_text(
            f"❌ *Invalid Code!*\n\nCode `{text}` not found.\nAvailable: INT001",
            parse_mode='Markdown'
        )
    
    conn.close()

# ===== BUTTON HANDLER =====
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "get_movie":
        await query.edit_message_text("🔍 Enter movie code (e.g., INT001)")
    
    elif query.data == "stats":
        user_id = update.effective_user.id
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        cursor.execute("SELECT requests_count, last_active FROM users WHERE user_id = ?", (user_id,))
        stats = cursor.fetchone()
        conn.close()
        if stats:
            text = f"📊 *Your Stats*\n\nMovies received: {stats[0]}\nLast active: {stats[1][:19]}"
        else:
            text = "📭 No statistics yet"
        await query.edit_message_text(text, parse_mode='Markdown')
    
    elif query.data == "movies_list":
        conn = sqlite3.connect('movies.db')
        cursor = conn.cursor()
        cursor.execute("SELECT code, title, year FROM movies")
        movies = cursor.fetchall()
        conn.close()
        if movies:
            text = "🎬 *Available Movies:*\n\n" + "\n".join([f"• {title} ({year}) - `{code}`" for code, title, year in movies])
        else:
            text = "📭 No movies available"
        await query.edit_message_text(text, parse_mode='Markdown')
    
    elif query.data == "help":
        text = "ℹ️ *Help*\n\nEnter movie code (INT001) or use /start"
        await query.edit_message_text(text, parse_mode='Markdown')

# ===== FLASK ROUTES =====
@app.route(f'/{TOKEN}', methods=['POST'])
async def webhook():
    """Telegram webhook"""
    try:
        update = Update.de_json(request.get_json(), application.bot)
        await application.process_update(update)
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

# ===== MAIN =====
if __name__ == '__main__':
    init_db()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    port = int(os.environ.get('PORT', 5000))
    app_name = os.environ.get('RENDER_EXTERNAL_HOSTNAME', 'localhost')
    webhook_url = f"https://{app_name}/{TOKEN}" if app_name != 'localhost' else f"http://localhost:{port}/{TOKEN}"
    
    try:
        application.bot.set_webhook(webhook_url)
        logging.info(f"Webhook set: {webhook_url}")
    except Exception as e:
        logging.error(f"Webhook error: {e}")
    
    app.run(host='0.0.0.0', port=port)
