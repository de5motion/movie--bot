"""
This file imports the Flask app from bot.py for Render.com
"""
from bot import app

# app is already defined in bot.py
# This file just re-exports it so Render can find it

if __name__ == "__main__":
    app.run()
