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