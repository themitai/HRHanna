import asyncio
import random
import os
from datetime import datetime, timezone
from telethon import TelegramClient, events, types
from openai import AsyncOpenAI

# --- [БЛОК НАСТРОЕК] ---
API_ID = 35523804          
API_HASH = 'ff7673ebc0e925a32fb52693bdfae16f'     
SESSION_NAME = 'hr_assistant_session'
REPORT_CHAT_ID = 7238685565 
RECRUITER_TAG = "@hannaober" 

# Берем API ключ из переменных окружения Railway
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Файлы базы
DB_FILE = "sent_users.txt"
KNOWN_CHATS_FILE = "known_chats.txt"

# --- [ИИ ЛОГИКА] ---

async def ai_analyze_message(text, mode="check_seeker"):
    """
    mode "check_seeker": Ищет ли человек работу?
    mode "check_interest": Согласен ли человек на инфо?
    """
    prompts = {
        "check_seeker": "Ты — HR-фильтр. Если сообщение от человека, который ищет работу, подработку или заработок (даже со сленгом или ошибками), ответь только 'ДА'. Если это реклама, вакансия от другого или просто вопрос — 'НЕТ'.",
        "check_interest": "Если человек проявил интерес к вакансии (сказал да, ок, пишите, что за работа, готов), ответь 'ДА'. Если отказался или спросил другое — 'НЕТ'."
    }
    
    try:
        response = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": prompts[mode]},
                {"role": "user", "content": text}
            ],
            max_tokens=5,
            temperature=0
        )
        result = response.choices[0].message.content.strip().upper()
        return "ДА" in result
    except Exception as e:
        print(f"Ошибка ИИ: {e}")
        return False

# --- [ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ] ---

def is_already_sent(user_id):
    if not os.path.exists(DB_FILE): return False
    with open(DB_FILE, "r") as f: return str(user_id) in f.read().splitlines()

def mark_as_sent(user_id):
    with open(DB_FILE, "a") as f: f.write(f"{user_id}\n")

# --- [ОСНОВНАЯ ЛОГИКА] ---

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

@client.on(events.NewMessage)
async def group_handler(event):
    if not event.is_group: return

    # Проверка нового чата
    if not os.path.exists(KNOWN_CHATS_FILE): open(KNOWN_CHATS_FILE, "w").close()
    with open(KNOWN_CHATS_FILE, "r+") as f:
        known = f.read().splitlines()
        if str(event.chat_id) not in known:
            chat = await event.get_chat()
            f.write(f"{event.chat_id}\n")
            await client.send_message(REPORT_CHAT_ID, f"✅ **ЧАТ ПОДКЛЮЧЕН:** «{chat.title}»")

    # Базовые фильтры
    if (datetime.now(timezone.utc) - event.date).total_seconds() > 60: return
    if not event.sender or not isinstance(event.sender, types.User) or event.sender.bot: return

    # ИИ Анализ
    is_seeker = await ai_analyze_message(event.raw_text, mode="check_seeker")
    
    if is_seeker:
        sender = event.sender
        if not is_already_sent(sender.id):
            user_link = f"tg://user?id={sender.id}"
            chat = await event.get_chat()
            
            # Сообщаем в отчет
            await client.send_message(REPORT_CHAT_ID, 
                f"🤖 **ИИ ЗАМЕТИЛ СОИСКАТЕЛЯ**\n👤: {sender.first_name}\n📍: {chat.title}\n📝: _{event.raw_text}_\n👉 [ОТКРЫТЬ ЧАТ]({user_link})")
            
            # Ждем как человек
            await asyncio.sleep(random.randint(240, 600))
            
            try:
                msg = "Здравствуйте! Увидела ваше сообщение в группе. У нас сейчас есть удаленная позиция в крипто-сфере (без опыта). Вам было бы интересно узнать подробности?"
                await client.send_message(sender.id, msg)
                mark_as_sent(sender.id)
            except:
                await client.send_message(REPORT_CHAT_ID, f"❌ Закрыты ЛС у `{sender.id}`")

@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def private_handler(event):
    if not event.sender or event.sender.bot: return
    
    # Проверяем интерес через ИИ
    is_interested = await ai_analyze_message(event.raw_text, mode="check_interest")
    
    if is_already_sent(event.sender_id) and is_interested:
        # Имитация набора текста
        await asyncio.sleep(random.randint(40, 90))
        
        offer_text = (
            f"Отлично! Суть проста: обработка входящих заявок по готовым инструкциям (обмен/конвертация). "
            f"Обучение за наш счет, работа полностью удаленная.\n\n"
            f"Чтобы начать или задать вопросы куратору, напишите нашему менеджеру: {RECRUITER_TAG}\n"
            f"Скажите, что вы от Ханны."
        )
        
        await event.reply(offer_text)
        
        # Уведомляем тебя, что лид "созрел"
        await client.send_message(REPORT_CHAT_ID, 
            f"🔥 **ЛИД ГОТОВ!**\nКандидат [id:{event.sender_id}](tg://user?id={event.sender_id}) ждет твоего сообщения или переходит к {RECRUITER_TAG}.")

async def main():
    await client.start()
    print("🤖 Бот с ИИ запущен...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
