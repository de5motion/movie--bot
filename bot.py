from flask import Flask, request, jsonify
import requests
import os

TOKEN = "8616873829:AAF0BF9bx4R4wEcMzvhk24zD75Kl82Ieedo"

app = Flask(__name__)

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    try:
        data = request.get_json()
        if data and "message" in data:
            chat_id = data["message"]["chat"]["id"]
            text = data["message"].get("text", "")
            
            # Просто отвечаем тем же текстом
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": f"You said: {text}"})
            
        return "ok"
    except Exception as e:
        return str(e), 500

@app.route('/')
def index():
    return "Test bot is running!"

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)