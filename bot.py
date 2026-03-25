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

# Храним статусы в памяти (для скорости)
user_db = {} 

STOP_PHRASES = ['ищем', 'вакансия', 'в офис', 'на склад', 'требуются', 'набираем', 'упаковке']

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# --- [ЛОГИКА ИИ] ---
async def ai_check(text, task="is_seeker"):
    prompts = {
        "is_seeker": "Человек пишет 'ищу работу' или 'нужна подработка'? Ответь только ДА или НЕТ.",
        "is_interested": "Человек хочет узнать подробности или согласен? Ответь только ДА или НЕТ."
    }
    try:
        res = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompts[task]}, {"role": "user", "content": text}],
            max_tokens=5
        )
        return "ДА" in res.choices[0].message.content.upper()
    except: return False

# --- [КЛИЕНТ] ---
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

@client.on(events.NewMessage)
async def handler(event):
    if not event.sender or event.sender.bot: return
    user_id = event.sender_id

    # А) ДИАЛОГ В ЛИЧКЕ
    if event.is_private:
        log(f"ЛС от {user_id}: {event.raw_text}")
        status = user_db.get(user_id)
        
        # Если бот уже что-то писал этому юзеру (любой статус кроме None)
        if status:
            if await ai_check(event.raw_text, "is_interested"):
                if status == "sent":
                    await event.reply("Условия: удаленно, крипто-сфера. ЗП: 2000€ + 2%. Обучение 2 дня. Подходит?")
                    user_db[user_id] = "offered"
                elif status == "offered":
                    await event.reply(f"Супер! Напишите куратору Ханне, она даст доступ к обучению: {RECRUITER_TAG}")
                    user_db[user_id] = "final"
                    await client.send_message(REPORT_CHAT_ID, f"🔥 **ЛИД ДОЖАТ:** @{event.sender.username or user_id}")

    # Б) ПОИСК В ГРУППАХ
    elif event.is_group:
        if (datetime.now(timezone.utc) - event.date).total_seconds() > 180: return
        
        text = event.raw_text.lower()
        if any(p in text for p in STOP_PHRASES): return

        if await ai_check(event.raw_text, "is_seeker"):
            if user_id not in user_db:
                chat = await event.get_chat()
                msg_link = f"https://t.me/c/{str(event.chat_id)[4:]}/{event.id}" if not chat.username else f"https://t.me/{chat.username}/{event.id}"
                
                # Подробный отчет в твой канал
                report = (
                    f"🎯 **ЛИД НАЙДЕН**\n"
                    f"👤 **Имя:** {event.sender.first_name}\n"
                    f"🆔 **ID:** `{user_id}`\n"
                    f"💬 **Текст:** {event.raw_text[:100]}\n"
                    f"📍 **Группа:** {chat.title}\n"
                    f"🔗 **Ссылка:** [ПЕРЕЙТИ]({msg_link})"
                )
                await client.send_message(REPORT_CHAT_ID, report, link_preview=False)
                
                # Имитация набора текста и отправка в ЛС
                user_db[user_id] = "sent"
                await asyncio.sleep(random.randint(15, 30))
                try:
                    await client.send_message(user_id, "Здравствуйте! Увидела ваш запрос в группе. У нас есть удаленная вакансия (крипто-сфера, без опыта). Интересно узнать детали?")
                except:
                    log(f"ЛС закрыты у {user_id}")

async def main():
    await client.start()
    log("🚀 БОТ ЗАПУЩЕН И ГОТОВ")
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
