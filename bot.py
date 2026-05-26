import logging
import sqlite3
import re
import telebot

TOKEN = "8660161351:AAEGsV68gS860oepV0c1nAxPUkjvBiskWdY"
ADMIN_ID = 6777360306  # Твой Telegram ID
PRIVATE_CHANNEL = -1003800629563

# Инициализируем бота через telebot
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')
logging.basicConfig(level=logging.INFO)

# Инициализация базы данных SQLite
def init_db():
    conn = sqlite3.connect('main_movies.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            title TEXT,
            year INTEGER,
            description TEXT,
            message_id INTEGER
        )
    ''')
    conn.commit()
    conn.close()
init_db()

# === МАССОВАЯ ЗАГРУЗКА СПИСКА (Только для тебя) ===
@bot.message_handler(func=lambda message: message.text and message.text.startswith('/загрузка') and message.from_user.id == ADMIN_ID)
def handle_bulk_upload(message):
    text = message.text.strip()
    lines = text.split('\n')
    
    conn = sqlite3.connect('main_movies.db')
    cursor = conn.cursor()
    
    added_count = 0
    for line in lines:
        line = line.strip()
        
        # Пропускаем команду, пустые строки и заголовки списка
        if not line or line.startswith('/загрузка') or "Available Movies" in line:
            continue
        
        # Убираем точку списка в начале строки
        line = line.lstrip('•').strip()
        
        # Парсим строки формата: "Название фильма (Год) - Код" или "Название 🎥 (0) - Код"
        match = re.search(r'^(.*?)\s*(?:🎥)?\s*\((\d+)\)\s*-\s*(\d+)$', line)
        if match:
            title = match.group(1).strip()
            year = int(match.group(2))
            code = match.group(3).strip()
            
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO movies (code, title, year, description, message_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (code, title, year, f"Фильм: {title}", 0))
                added_count += 1
            except Exception as e:
                logging.error(f"Ошибка вставки в БД: {e}")
    
    conn.commit()
    conn.close()
    bot.reply_to(message, f"✅ <b>Система восстановления:</b> успешно загружено <b>{added_count}</b> фильмов!")

# === СТАНДАРТНАЯ КОМАНДА /START ===
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🎬 Добро пожаловать!\n\nВведите числовой <b>код фильма</b>, чтобы получить ссылку.")

# === ПОИСК ПО КОДУ (Для всех пользователей) ===
@bot.message_handler(func=lambda message: message.text and message.text.isdigit())
def search_movie(message):
    code = message.text.strip()
    
    conn = sqlite3.connect('main_movies.db')
    cursor = conn.cursor()
    cursor.execute("SELECT title, year, description, message_id FROM movies WHERE code=?", (code,))
    movie = cursor.fetchone()
    conn.close()

    if movie:
        m_title, m_year, m_desc, m_msg_id = movie
        clean_id = str(PRIVATE_CHANNEL).replace('-100', '')
        
        # Если message_id равен 0 (после массовой загрузки), даем общую ссылку на канал
        if m_msg_id == 0:
            movie_link = f"https://t.me/c/{clean_id}"
        else:
            movie_link = f"https://t.me/c/{clean_id}/{m_msg_id}"
        
        response_text = (
            f"🎬 <b>{m_title} ({m_year if m_year != 0 else 'год не указан'})</b>\n\n"
            f"🍿 <a href='{movie_link}'>СМОТРЕТЬ ФИЛЬМ В КАНАЛЕ</a>"
        )
        bot.reply_to(message, response_text)
    else:
        bot.reply_to(message, "❌ Фильм с таким кодом не найден в базе.")

# === ЕСЛИ ПОЛЬЗОВАТЕЛЬ СКИПНУЛ ШАБЛОН ===
@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    bot.reply_to(message, "⚠️ Пожалуйста, отправьте корректный числовой код фильма (только цифры).")

# Удаляем старый вебхук перед запуском, чтобы очистить пути для Telegram
try:
    telebot.TeleBot(TOKEN).delete_webhook()
    logging.info("✅ Старый вебхук успешно удален. Переходим на Long Polling!")
except Exception as e:
    logging.error(f"Ошибка удаления вебхука: {e}")

# Запуск постоянного опроса серверов Telegram
if __name__ == "__main__":
    logging.info("🚀 Бот запущен в режиме Infinity Polling...")
    bot.infinity_polling()
