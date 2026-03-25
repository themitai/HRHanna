import asyncio
import random
import os
from datetime import datetime, timezone
from telethon import TelegramClient, events
from openai import AsyncOpenAI

# --- [КОНФИГУРАЦИЯ] ---
API_ID = 35523804          
API_HASH = 'ff7673ebc0e925a32fb52693bdfae16f'     
SESSION_NAME = 'hr_assistant_session'
REPORT_CHAT_ID = 7238685565 
RECRUITER_TAG = "@hannaober"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# СЛОВАРЬ ДЛЯ СТАТУСОВ (вместо файла)
# Это будет работать, пока бот запущен. 
user_db = {} 

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# --- [ЛОГИКА ИИ] ---
async def ai_is_interested(text):
    try:
        response = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Если человек проявляет интерес к работе, хочет подробности или согласен — ответь ДА. В остальных случаях — НЕТ."},
                {"role": "user", "content": text}
            ],
            max_tokens=5
        )
        return "ДА" in response.choices[0].message.content.upper()
    except:
        return True

async def ai_is_seeker(text):
    try:
        response = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Ты HR. Если человек ИЩЕТ работу (я ищу, нужна работа) — ответь ДА. Если ПРЕДЛАГАЕТ — НЕТ."},
                {"role": "user", "content": text}
            ],
            max_tokens=5
        )
        return "ДА" in response.choices[0].message.content.upper()
    except:
        return False

# --- [ОСНОВНОЙ КЛИЕНТ] ---
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

@client.on(events.NewMessage)
async def handler(event):
    if not event.sender or event.sender.bot: return
    user_id = event.sender_id

    # А) ЛИЧКА (ВЕДЕМ ДИАЛОГ)
    if event.is_private:
        status = user_db.get(user_id)
        log(f"ЛС от {user_id}. Текст: {event.raw_text}. Статус в памяти: {status}")

        if status == "sent":
            if await ai_is_interested(event.raw_text):
                await asyncio.sleep(2)
                await event.reply(
                    "Условия: удаленно, крипто-сфера (обработка заявок). "
                    "ЗП: 2000€/мес + 2%. Обучаем с нуля. Вам подходит такой формат?"
                )
                user_db[user_id] = "offered"
                log(f"Юзер {user_id} переведен в статус offered")
        
        elif status == "offered":
            if await ai_is_interested(event.raw_text):
                await asyncio.sleep(2)
                await event.reply(f"Прекрасно! Для связи с куратором и записи на обучение напишите Ханне: {RECRUITER_TAG}")
                user_db[user_id] = "final"
                await client.send_message(REPORT_CHAT_ID, f"🔥 **ЛИД ГОТОВ!** Юзер @{event.sender.username if event.sender.username else user_id}")

    # Б) ГРУППЫ (ИЩЕМ НОВЫХ)
    elif event.is_group:
        if (datetime.now(timezone.utc) - event.date).total_seconds() > 60: return
        
        if await ai_is_seeker(event.raw_text):
            if user_id not in user_db:
                log(f"Найден новый соискатель: {user_id}")
                await client.send_message(REPORT_CHAT_ID, f"🔎 **ЛИД:** {event.sender.first_name}\n📝: {event.raw_text[:60]}")
                
                await asyncio.sleep(random.randint(15, 30))
                try:
                    await client.send_message(user_id, "Здравствуйте! Увидела ваш запрос в группе. У нас сейчас открыта удаленная позиция (крипто-сфера, без опыта). Вам интересно узнать детали?")
                    user_db[user_id] = "sent"
                except:
                    log(f"Не удалось написать {user_id} (ЛС закрыты)")

async def main():
    log("Запуск бота...")
    await client.start()
    log("🚀 БОТ ОНЛАЙН")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
