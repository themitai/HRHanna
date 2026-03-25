import asyncio
import os
import sqlite3
import random
import sys
from datetime import datetime, timezone
from telethon import TelegramClient, events
from openai import AsyncOpenAI
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- [КОНФИГУРАЦИЯ] ---
API_ID = 35523804
API_HASH = 'ff7673ebc0e925a32fb52693bdfae16f'
REPORT_CHAT_ID = 7238685565
RECRUITER_TAG = "@hannaober"

# Секреты
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Пути (используем Volume /app/data/)
DB_PATH = '/app/data/bot_data.db' if os.path.exists('/app/data') else 'bot_data.db'
SESSION_PATH = '/app/data/hr_session' if os.path.exists('/app/data') else 'hr_session'

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# --- [DIAGNOSTICS: ПРОВЕРКА ИИ] ---
async def ai_check(text, mode="is_seeker"):
    log(f"🔎 ИИ ПРОВЕРКА: '{text[:30]}...'")
    
    if not OPENAI_API_KEY:
        log("❌ ОШИБКА: Переменная OPENAI_API_KEY пуста!")
        return True if mode == "is_interest" else False

    try:
        # Пытаемся сделать запрос
        res = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты HR. Отвечай только ДА или НЕТ."},
                {"role": "user", "content": f"Режим: {mode}. Текст: {text}"}
            ],
            max_tokens=5,
            timeout=10.0 # Ждем максимум 10 секунд
        )
        answer = res.choices[0].message.content.strip().upper()
        log(f"✅ ИИ ОТВЕТИЛ: {answer} (Ключ работает)")
        return "ДА" in answer

    except Exception as e:
        # Вот тут мы понимаем, ПОЧЕМУ не работает
        error_msg = str(e).lower()
        if "insufficient_quota" in error_msg:
            log("❌ ИИ ОШИБКА: На счету OpenAI закончились деньги (Баланс 0$)")
        elif "invalid_api_key" in error_msg:
            log("❌ ИИ ОШИБКА: Неверный API Key. Проверь пробелы в Railway.")
        elif "rate_limit" in error_msg:
            log("❌ ИИ ОШИБКА: Слишком много запросов (Rate Limit).")
        else:
            log(f"❌ ИИ ТЕХНИЧЕСКАЯ ОШИБКА: {e}")
        
        # Если ИИ упал, разрешаем диалог в личке (чтобы не терять лида), 
        # но запрещаем спам в группах (чтобы не писать всем подряд)
        return True if mode == "is_interest" else False

# --- [SERVICE: СЕРВЕР ДЛЯ RAILWAY] ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# --- [DB: БАЗА ДАННЫХ] ---
def init_db():
    if os.path.dirname(DB_PATH): os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, status TEXT)')
    conn.close()

def get_status(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT status FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        return row[0] if row else None
    except: return None

def set_status(user_id, status):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT OR REPLACE INTO users (user_id, status) VALUES (?, ?)", (user_id, status))
        conn.commit()
        conn.close()
    except: pass

# --- [BOT: ОБРАБОТКА СООБЩЕНИЙ] ---
init_db()
client = TelegramClient(SESSION_PATH, API_ID, API_HASH)

@client.on(events.NewMessage)
async def handler(event):
    if not event.sender or event.sender.bot: return
    uid = event.sender_id

    # ЛОГ: Бот видит сообщение
    log(f"📩 [{ 'ЛС' if event.is_private else 'ГРУППА' }] Сообщение от {uid}")

    if event.is_private:
        status = get_status(uid)
        if status in ["sent", "offered"]:
            if await ai_check(event.raw_text, "is_interest"):
                if status == "sent":
                    await event.reply("💼 Удаленно, крипто. ЗП: 2000€ + 2%. Подходит?")
                    set_status(uid, "offered")
                else:
                    await event.reply(f"Пишите куратору Ханне: {RECRUITER_TAG}")
                    set_status(uid, "final")
                    await client.send_message(REPORT_CHAT_ID, f"🔥 ЛИД ДОЖАТ: @{event.sender.username or uid}")

    elif event.is_group:
        if (datetime.now(timezone.utc) - event.date).total_seconds() > 300: return
        if await ai_check(event.raw_text, "is_seeker"):
            if get_status(uid) is None:
                log(f"🎯 ЛИД В ГРУППЕ: {uid}")
                set_status(uid, "sent")
                await asyncio.sleep(random.randint(20, 40))
                try: 
                    await client.send_message(uid, "Здравствуйте! Увидела ваш запрос в группе. У нас есть удаленка. Интересно?")
                except: log(f"❌ Не удалось написать в ЛС {uid} (закрыто)")

async def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    await client.start()
    log("🚀 БОТ ЗАПУЩЕН И СЛУШАЕТ СООБЩЕНИЯ")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
