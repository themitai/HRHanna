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

# Секреты из Railway
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SESSION_STR = os.getenv("TELEGRAM_SESSION")

ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
DB_PATH = '/app/data/bot_data.db' if os.path.exists('/app/data') else 'bot_data.db'

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# --- [БАЗА ДАННЫХ] ---
def init_db():
    if os.path.dirname(DB_PATH):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, status TEXT)''')
    conn.commit()
    conn.close()

def get_status(user_id):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM users WHERE user_id=?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except: return None

def set_status(user_id, status):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO users (user_id, status) VALUES (?, ?)", (user_id, status))
        conn.commit()
        conn.close()
    except: pass

# --- [ЖЕСТКАЯ ПРОВЕРКА ИИ] ---
async def ai_check(text, mode="is_seeker"):
    log(f"🤖 Запрос к ИИ (режим {mode}): {text[:50]}...")
    
    prompts = {
        "is_seeker": (
            "Ты — строгий HR-фильтр. Твоя цель: найти только тех, кто ИЩЕТ работу. "
            "Если текст похож на резюме или фразу 'Ищу работу', 'Нужен ворк', 'Возьмусь за работу' — ответь ДА. "
            "Если в тексте предлагают услуги (ФНС, пробив, дизайн, ремонт) или предлагают вакансию (ищем в команду, требуется) — ответь НЕТ. "
            "Отвечай только ДА или НЕТ."
        ),
        "is_interest": (
            "Человек ответил на предложение работы. "
            "Если он согласен, хочет узнать детали или пишет 'Да', 'Интересно', 'Расскажите' — ответь ДА. "
            "Если он отказывается или пишет бред — ответь НЕТ. "
            "Отвечай только ДА или НЕТ."
        )
    }
    
    try:
        res = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompts[mode]},
                {"role": "user", "content": text}
            ],
            max_tokens=5,
            temperature=0
        )
        answer = res.choices[0].message.content.strip().upper()
        log(f"🤖 Ответ ИИ: {answer}")
        return "ДА" in answer
    except Exception as e:
        log(f"❌ ОШИБКА OpenAI: {e}")
        return False

# --- [ОСНОВНОЙ ОБРАБОТЧИК] ---
init_db()
if not SESSION_STR:
    log("ОШИБКА: Нет TELEGRAM_SESSION")
    sys.exit(1)

client = TelegramClient(StringSession(SESSION_STR), API_ID, API_HASH)

@client.on(events.NewMessage)
async def handler(event):
    if not event.sender or event.sender.bot: return
    user_id = event.sender_id

    # 1. ЛИЧКА (Диалог)
    if event.is_private:
        status = get_status(user_id)
        if not status: return # Игнорим тех, кого не находили
        
        log(f"📩 Сообщение в ЛС от {user_id}: {event.raw_text}")
        
        # Если бот уже отправил первое сообщение и ждет реакции
        if status == "sent":
            if await ai_check(event.raw_text, "is_interest"):
                await event.reply(
                    "💼 **Вариант работы:** Удаленно (обработка входящих заявок).\n"
                    "• Оплата: 2000€ фиксированно + 2% от объема.\n"
                    "• Обучение: 2 дня (бесплатно).\n\n"
                    "Интересно? Напишите 'Да', и я дам контакт куратора."
                )
                set_status(user_id, "offered")
            else:
                log("ИИ решил, что юзеру не интересно.")

        # Если бот скинул условия и ждет финального согласия
        elif status == "offered":
            if await ai_check(event.raw_text, "is_interest"):
                await event.reply(f"Отлично! Напишите куратору Ханне: {RECRUITER_TAG}")
                set_status(user_id, "final")
                await client.send_message(REPORT_CHAT_ID, f"🔥 **ЛИД ГОТОВ:** @{event.sender.username or user_id}")

    # 2. ГРУППЫ (Поиск)
    elif event.is_group:
        # Не смотрим старое
        if (datetime.now(timezone.utc) - event.date).total_seconds() > 180: return
        
        # Только если ИИ подтвердил, что это СОИСКАТЕЛЬ
        if await ai_check(event.raw_text, "is_seeker"):
            if get_status(user_id) is None:
                chat = await event.get_chat()
                msg_link = f"https://t.me/c/{str(event.chat_id)[4:]}/{event.id}" if not chat.username else f"https://t.me/{chat.username}/{event.id}"
                
                # Отчет
                await client.send_message(REPORT_CHAT_ID, f"🎯 **ЛИД НАЙДЕН**\n👤 {event.sender.first_name}\n💬 {event.raw_text[:120]}\n🔗 [ПЕРЕЙТИ]({msg_link})")
                
                # Ставим статус и пишем в ЛС
                set_status(user_id, "sent")
                await asyncio.sleep(random.randint(20, 40))
                try:
                    await client.send_message(user_id, "Здравствуйте! Увидела ваш запрос в группе. У нас есть удаленная вакансия (крипто-сфера, без опыта). Вам интересно узнать детали?")
                    log(f"✅ Успешно написали лиду {user_id} в ЛС")
                except Exception as e:
                    log(f"⚠️ Не смогли написать {user_id} в ЛС: {e}")

async def main():
    await client.start()
    log("🚀 БОТ ЗАПУЩЕН НА СТРОГОМ ИИ")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
