import asyncio
import os
import sqlite3
import random
import threading
from datetime import datetime, timezone

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import User
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
DB_PATH = os.getenv("DB_PATH", "bot_final_v7.db")

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# --- HEALTH SERVER (Railway) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args): return

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# --- БАЗА ДАННЫХ ---
def init_db():
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
        log(f"💾 Статус ID {user_id} -> {status}")
    except Exception as e: log(f"❌ Ошибка БД: {e}")

# --- ИИ МОЗГ ---
async def ai_check(text, mode="is_seeker"):
    if not text or len(text) < 2: return False
    log(f"🔎 ИИ проверка ({mode}): {text[:40]}...")
    try:
        if mode == "is_seeker":
            sys_prompt = "Ты HR. Ответь ДА, только если человек САМ ищет работу. НЕТ — если это вакансия, реклама или спам."
        else:
            sys_prompt = "Клиент ответил на предложение. Он заинтересован? Ответь ТОЛЬКО ДА или НЕТ."

        res = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": text}],
            max_tokens=5, temperature=0
        )
        ans = res.choices[0].message.content.strip().upper()
        log(f"✅ ИИ вердикт: {ans}")
        return "ДА" in ans
    except Exception as e:
        log(f"❌ Ошибка ИИ: {e}")
        return False

# --- ОБРАБОТЧИК СООБЩЕНИЙ ---
init_db()
client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)

@client.on(events.NewMessage)
async def handler(event):
    if not event.sender_id: return
    
    # Игнорируем ботов и каналы
    is_bot = getattr(event.sender, 'bot', False) if hasattr(event.sender, 'bot') else False
    if not isinstance(event.sender, User) or is_bot: return

    uid = event.sender_id
    text = event.raw_text.strip()
    
    # Формируем данные пользователя
    first_name = event.sender.first_name or "User"
    username = f"@{event.sender.username}" if event.sender.username else "Нет юзернейма"
    user_link = f"tg://user?id={uid}"

    # 1. ОБРАБОТКА ЛИЧНЫХ СООБЩЕНИЙ (Ответы на рассылку)
    if event.is_private:
        status = get_status(uid)
        if status in ("sent", "offered"):
            log(f"📩 ЛС от {username}: {text}")
            if await ai_check(text, "is_interest"):
                await asyncio.sleep(random.randint(5, 10)) # Имитация печати
                if status == "sent":
                    await event.reply(
                        "💼 **Наши условия:**\n"
                        "• Удаленная работа (крипто-направление)\n"
                        "• Оплата: 2000€ фиксированно + 2% бонус\n"
                        "• Обучение предоставляем (2 дня)\n\n"
                        "Подскажите, вам было бы интересно попробовать?"
                    )
                    set_status(uid, "offered")
                elif status == "offered":
                    await event.reply(f"Супер! Для старта обучения напишите нашему куратору: {RECRUITER_TAG}")
                    set_status(uid, "final")
                    await client.send_message(REPORT_CHAT_ID, f"🔥 **ЛИД ГОТОВ!**\n👤 {first_name} ({username})\n🔗 [ПЕРЕЙТИ К ЛИДУ]({user_link})", link_preview=False)
        return

    # 2. ОБРАБОТКА ГРУПП (Поиск соискателей)
    if not event.is_group: return
    if (datetime.now(timezone.utc) - event.date).total_seconds() > 600: return

    if await ai_check(text, "is_seeker") and get_status(uid) is None:
        try:
            chat = await event.get_chat()
            group_name = chat.title
            log(f"🎯 Найден соискатель: {username}")

            # 1. Сразу отправляем подробный отчет в твой канал
            report_msg = (
                f"🎯 **НОВЫЙ ЛИД ОБНАРУЖЕН**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 **Имя:** {first_name}\n"
                f"🆔 **Username:** {username}\n"
                f"🏢 **Группа:** {group_name}\n"
                f"📝 **Сообщение:** {text[:150]}\n"
                f"🔗 **Ссылка:** [ОТКРЫТЬ ПРОФИЛЬ]({user_link})"
            )
            await client.send_message(REPORT_CHAT_ID, report_msg, link_preview=False)
            
            # Ставим статус, чтобы не писать повторно
            set_status(uid, "sent")

            # 2. Анти-спам пауза перед отправкой в ЛС (от 1 до 2.5 минут)
            delay = random.randint(60, 150)
            log(f"⏳ Пауза {delay} сек перед отправкой сообщения в ЛС...")
            await asyncio.sleep(delay)

            # 3. Отправка первого сообщения в ЛС
            await client.send_message(uid, "Здравствуйте! Увидела ваше сообщение в группе. У нас сейчас открыта удаленная вакансия (крипто-направление). Вам было бы интересно узнать подробности?")
            log(f"✅ Сообщение успешно отправлено к {username}")

        except Exception as e:
            if "Too many requests" in str(e):
                log("⚠️ Telegram ограничил отправку (FloodWait). Ждем...")
            else:
                log(f"❌ Ошибка: {e}")

# --- ЗАПУСК ---
async def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    await client.start()
    log("🚀 БОТ ЗАПУЩЕН И МОНИТОРИТ ЧАТЫ")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
