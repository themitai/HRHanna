import asyncio
import os
import sqlite3
import random
import threading
import sys
from datetime import datetime, timezone

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from openai import AsyncOpenAI
from http.server import BaseHTTPRequestHandler, HTTPServer

# --- КОНФИГУРАЦИЯ ---
API_ID = 35523804
API_HASH = 'ff7673ebc0e925a32fb52693bdfae16f'
REPORT_CHAT_ID = 7238685565
RECRUITER_TAG = "@hannaober"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SESSION_STR = os.getenv("TELEGRAM_SESSION")

ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
DB_PATH = '/app/data/bot_data.db' if os.path.exists('/app/data') else 'bot_data.db'

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# --- HEALTH SERVER ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"WORKING")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# --- БАЗА ДАННЫХ ---
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, status TEXT)')
    conn.close()

def get_status(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT status FROM users WHERE user_id=?", (user_id,)).fetchone()
        conn.close()
        return row[0] if row else None
    except:
        return None

def set_status(user_id, status):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT OR REPLACE INTO users (user_id, status) VALUES (?, ?)", (user_id, status))
        conn.commit()
        conn.close()
    except Exception as e:
        log(f"Ошибка SQLite: {e}")

# --- ИИ ---
async def ai_check(text, mode="is_seeker"):
    log(f"🔎 ИИ ({mode}): {text[:60]}...")
    try:
        if mode == "is_seeker":
            sys_prompt = (
                "Отвечай ТОЛЬКО одним словом ДА или НЕТ. "
                "ДА — только если человек САМ ищет работу. "
                "НЕТ — если предлагает вакансию, услуги, работу другим людям."
            )
        else:
            sys_prompt = (
                "Человек проявил интерес к вакансии? "
                "да, давай, подробнее, интересно, хочу, ок, хорошо — это ДА. "
                "Отвечай ТОЛЬКО ДА или НЕТ."
            )

        res = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": text}],
            max_tokens=8,
            temperature=0
        )
        ans = res.choices[0].message.content.strip().upper()
        log(f"✅ ИИ вердикт ({mode}): {ans}")
        return "ДА" in ans
    except Exception as e:
        log(f"❌ Ошибка OpenAI: {e}")
        return False

# --- КЛИЕНТ ---
init_db()
client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)

@client.on(events.NewMessage)
async def handler(event):
    if not event.sender or event.sender.bot:
        return

    uid = event.sender_id
    text = event.raw_text.strip()
    first_name = event.sender.first_name or "User"

    # ====================== ЛИЧНЫЕ СООБЩЕНИЯ (самая важная часть) ======================
    if event.is_private or event.chat_id == uid:
        status = get_status(uid)
        log(f"[ЛИЧКА] Сообщение от {uid} ({first_name}) | статус={status} | текст: '{text}'")

        if status in ("sent", "offered"):
            if await ai_check(text, "is_interest"):
                log(f"[ЛИЧКА] ИИ подтвердил интерес от {uid}")

                if status == "sent":
                    await event.reply(
                        "💼 **Условия работы:**\n"
                        "• Удаленно (крипто-сфера)\n"
                        "• ЗП: 2000€ + 2% бонус\n"
                        "• Обучение 2 дня. График гибкий.\n\n"
                        "Вам подходит такое?"
                    )
                    set_status(uid, "offered")
                    log(f"[ЛИЧКА] Отправили условия → {uid}")

                elif status == "offered":
                    await event.reply(f"Супер! Напишите куратору: {RECRUITER_TAG}")
                    set_status(uid, "final")
                    await client.send_message(
                        REPORT_CHAT_ID,
                        f"🔥 **ЛИД ДОЖАТ:** {first_name} (ID: {uid})"
                    )
                    log(f"[ЛИЧКА] ЛИД ДОЖАТ → {uid}")
            else:
                log(f"[ЛИЧКА] ИИ сказал НЕТ интересу от {uid}")
        return

    # ====================== ГРУППЫ ======================
    if not event.is_group:
        return
    if (datetime.now(timezone.utc) - event.date).total_seconds() > 300:
        return

    if await ai_check(event.raw_text, "is_seeker"):
        if get_status(uid) is None:
            try:
                chat = await event.get_chat()
                msg_link = f"https://t.me/{chat.username}/{event.id}" if chat.username else \
                           f"https://t.me/c/{str(event.chat_id)[4:]}/{event.id}"

                report = (
                    f"🎯 **НАЙДЕН СОИСКАТЕЛЬ**\n"
                    f"👤 {first_name}\n"
                    f"🆔 `{uid}`\n"
                    f"💬 {event.raw_text[:150]}\n"
                    f"📍 {chat.title}\n"
                    f"🔗 [Ссылка]({msg_link})"
                )
                await client.send_message(REPORT_CHAT_ID, report, link_preview=False)

                set_status(uid, "sent")
                await asyncio.sleep(random.randint(25, 55))

                await client.send_message(
                    uid,
                    "Здравствуйте! Увидела ваш запрос в группе. У нас сейчас открыта удаленная вакансия (крипто-направление). Вам было бы интересно узнать детали?"
                )
                log(f"✅ Написали в ЛС {uid}")
            except Exception as e:
                log(f"❌ Ошибка при работе с лидом {uid}: {e}")

# --- ЗАПУСК ---
async def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    await client.start()
    log("🚀 СТРОГИЙ БОТ-HR ЗАПУЩЕН (исправлена обработка ЛС)")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
