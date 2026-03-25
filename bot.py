import asyncio
import random
import os
import sqlite3
import sys
from datetime import datetime, timezone
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from openai import AsyncOpenAI

# --- [КОНФИГУРАЦИЯ] ---
API_ID = 35523804          
API_HASH = 'ff7673ebc0e925a32fb52693bdfae16f'
REPORT_CHAT_ID = 7238685565 
RECRUITER_TAG = "@hannaober"

# Берем секреты из переменных Railway
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SESSION_STR = os.getenv("TELEGRAM_SESSION")

ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Путь к базе данных на диске Railway Volume
DB_PATH = '/app/data/bot_data.db' if os.path.exists('/app/data') else 'bot_data.db'

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# --- [РАБОТА С БАЗОЙ SQLITE] ---
def init_db():
    if os.path.dirname(DB_PATH):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, status TEXT)''')
    conn.commit()
    conn.close()

def get_status(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def set_status(user_id, status):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, status) VALUES (?, ?)", (user_id, status))
    conn.commit()
    conn.close()

# --- [ЛОГИКА ИИ] ---
async def ai_check(text, mode="is_seeker"):
    # Черный список слов (сразу отсекаем предложения услуг и вакансий)
    STOP_LIST = ['ищем', 'вакансия', 'в офис', 'на склад', 'требуются', 'набираем', 'фнс', 'выполняю', 'услуги']
    if mode == "is_seeker" and any(s in text.lower() for s in STOP_LIST):
        return False

    prompts = {
        "is_seeker": "Ты HR. Если человек ИЩЕТ работу (я ищу, нужна работа) — ответь ДА. Если ПРЕДЛАГАЕТ услуги или вакансию — НЕТ.",
        "is_interest": "Человек проявил интерес к предложению (да, подробнее, согласен)? Ответь ДА или НЕТ."
    }
    try:
        res = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompts[mode]}, {"role": "user", "content": text}],
            max_tokens=5, temperature=0
        )
        return "ДА" in res.choices[0].message.content.upper()
    except Exception as e:
        log(f"Ошибка ИИ: {e}")
        return False

# --- [ОСНОВНОЙ КЛИЕНТ] ---
if not SESSION_STR:
    log("КРИТИЧЕСКАЯ ОШИБКА: TELEGRAM_SESSION не задана!")
    sys.exit(1)

init_db()
client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)

@client.on(events.NewMessage)
async def handler(event):
    if not event.sender or event.sender.bot: return
    user_id = event.sender_id

    # 1. ДИАЛОГ В ЛИЧКЕ
    if event.is_private:
        log(f"ЛС от {user_id}: {event.raw_text[:50]}")
        status = get_status(user_id)
        
        if status == "sent":
            # На первый ответ в ЛС отвечаем всегда, если есть хоть какой-то интерес
            if await ai_check(event.raw_text, "is_interest"):
                await event.reply(
                    "💼 **Детали вакансии:**\n• Удаленно, крипто-сфера.\n• ЗП: 2000€ + 2% бонуса.\n"
                    "• Обучение 2 дня. График гибкий.\n\nВам подходит такой формат?"
                )
                set_status(user_id, "offered")
        
        elif status == "offered":
            if await ai_check(event.raw_text, "is_interest"):
                await event.reply(f"Отлично! Напишите куратору Ханне для старта: {RECRUITER_TAG}")
                set_status(user_id, "final")
                await client.send_message(REPORT_CHAT_ID, f"🔥 **ЛИД ДОЖАТ!** Кандидат: @{event.sender.username or user_id}")

    # 2. ПОИСК В ГРУППАХ
    elif event.is_group:
        if (datetime.now(timezone.utc) - event.date).total_seconds() > 120: return
        
        if await ai_check(event.raw_text, "is_seeker"):
            if get_status(user_id) is None:
                chat = await event.get_chat()
                msg_link = f"https://t.me/c/{str(event.chat_id)[4:]}/{event.id}" if not chat.username else f"https://t.me/{chat.username}/{event.id}"
                
                # Отчет в твой канал
                report = (
                    f"🎯 **ЛИД НАЙДЕН**\n👤 **Имя:** {event.sender.first_name}\n"
                    f"💬 **Текст:** {event.raw_text[:100]}\n📍 **Группа:** {chat.title}\n🔗 [ПЕРЕЙТИ]({msg_link})"
                )
                await client.send_message(REPORT_CHAT_ID, report, link_preview=False)
                
                # Пишем приветствие в ЛС
                set_status(user_id, "sent")
                await asyncio.sleep(random.randint(15, 30))
                try:
                    await client.send_message(user_id, "Здравствуйте! Увидела ваш запрос в группе. У нас сейчас открыта удаленная позиция (крипто-сфера, без опыта). Вам интересно узнать детали?")
                except:
                    log(f"ЛС закрыты для {user_id}")

async def main():
    await client.start()
    log("🚀 БОТ ЗАПУЩЕН И ГОТОВ К РАБОТЕ")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
