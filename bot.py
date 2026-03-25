import asyncio
import os
import sqlite3
import random
import threading
from datetime import datetime, timezone
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from openai import AsyncOpenAI
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- [КОНФИГУРАЦИЯ] ---
API_ID = 35523804
API_HASH = 'ff7673ebc0e925a32fb52693bdfae16f'
REPORT_CHAT_ID = 7238685565
RECRUITER_TAG = "@hannaober"

# Секреты из Railway
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SESSION_STR = os.getenv("TELEGRAM_SESSION")

ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
DB_PATH = '/app/data/bot_data.db' if os.path.exists('/app/data') else 'bot_data.db'

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# --- [ОБМАНКА ДЛЯ RAILWAY] ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# --- [БАЗА ДАННЫХ] ---
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

# --- [ПРОВЕРКА ИИ С ДИАГНОСТИКОЙ] ---
async def ai_check(text, mode="is_seeker"):
    log(f"🔎 ПРОВЕРКА ИИ ({mode}): '{text[:30]}...'")
    if not OPENAI_API_KEY:
        log("❌ ОШИБКА: OPENAI_API_KEY не задан!")
        return True if mode == "is_interest" else False

    try:
        prompts = {
            "is_seeker": "Ты HR. Ответь ДА, только если человек ИЩЕТ работу. Если ПРЕДЛАГАЕТ — ответь НЕТ.",
            "is_interest": "Человек проявил интерес к вакансии (пишет 'да', 'подробнее', 'что за работа')? Ответь ДА или НЕТ."
        }
        res = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompts[mode]}, {"role": "user", "content": text}],
            max_tokens=5, timeout=15
        )
        ans = res.choices[0].message.content.strip().upper()
        log(f"✅ ИИ ОТВЕТИЛ: {ans}")
        return "ДА" in ans
    except Exception as e:
        log(f"❌ ОШИБКА ИИ: {e}")
        return True if mode == "is_interest" else False

# --- [КЛИЕНТ] ---
init_db()
client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)

@client.on(events.NewMessage)
async def handler(event):
    if not event.sender or event.sender.bot: return
    uid = event.sender_id
    username = f"@{event.sender.username}" if event.sender.username else f"ID: {uid}"
    first_name = event.sender.first_name or "Без имени"

    # 1. ЛИЧКА (Диалог)
    if event.is_private:
        status = get_status(uid)
        log(f"📩 ЛС от {username}: {event.raw_text[:30]} (Статус: {status})")
        
        if status in ["sent", "offered"]:
            if await ai_check(event.raw_text, "is_interest"):
                if status == "sent":
                    await event.reply("💼 **Условия работы:**\n• Удаленно (крипто-проект)\n• Оплата: 2000€ + 2% бонус\n• Обучение: 2 дня (бесплатно)\n\nВам подходит такое направление?")
                    set_status(uid, "offered")
                    log(f"✅ Условия отправлены {username}")
                elif status == "offered":
                    await event.reply(f"Отлично! Напишите нашему куратору Ханне для старта: {RECRUITER_TAG}")
                    set_status(uid, "final")
                    await client.send_message(REPORT_CHAT_ID, f"🔥 **ЛИД ГОТОВ:**\n👤 {first_name} ({username})\n✅ Согласился на условия.")
                    log(f"🔥 Лид {username} дожат!")

    # 2. ГРУППЫ (Поиск)
    elif event.is_group:
        if (datetime.now(timezone.utc) - event.date).total_seconds() > 600: return
        
        if await ai_check(event.raw_text, "is_seeker"):
            if get_status(uid) is None:
                chat = await event.get_chat()
                group_name = chat.title
                msg_link = f"https://t.me/c/{str(event.chat_id)[4:]}/{event.id}" if not chat.username else f"https://t.me/{chat.username}/{event.id}"
                
                log(f"🎯 ЛИД В ГРУППЕ '{group_name}': {username}")
                
                # ПОДРОБНЫЙ ОТЧЕТ
                report = (
                    f"🎯 **НОВЫЙ ЛИД**\n"
                    f"👤 **Кто:** {first_name} ({username})\n"
                    f"🏢 **Группа:** {group_name}\n"
                    f"📝 **Текст:** {event.raw_text}\n"
                    f"🔗 [ПЕРЕЙТИ К СООБЩЕНИЮ]({msg_link})"
                )
                await client.send_message(REPORT_CHAT_ID, report, link_preview=False)
                
                # Пишем в ЛС
                set_status(uid, "sent")
                await asyncio.sleep(random.randint(25, 50))
                try: 
                    await client.send_message(uid, "Здравствуйте! Увидела ваш запрос в группе. У нас сейчас открыта удаленная вакансия (крипто-сфера). Вам интересно узнать детали?")
                    log(f"✅ Приветствие отправлено {username}")
                except: 
                    log(f"❌ ЛС закрыты у {username}")
                    await client.send_message(REPORT_CHAT_ID, f"⚠️ Не удалось написать в ЛС {username} (закрыто).")

async def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    await client.start()
    log("🚀 БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
