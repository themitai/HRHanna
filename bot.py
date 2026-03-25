import asyncio
import random
import os
from datetime import datetime, timezone
from telethon import TelegramClient, events, types

# --- [НАСТРОЙКИ] ---
API_ID = 35523804          
API_HASH = 'ff7673ebc0e925a32fb52693bdfae16f'     
SESSION_NAME = 'hr_assistant_session'
REPORT_CHAT_ID = 7238685565 
RECRUITER_TAG = "@hannaober" 

# --- [ТЕКСТЫ] ---
FIRST_QUESTION = "Здравствуйте! Увидела ваш запрос в группе по поиску работы. У нас сейчас открыта позиция в криптовалютном направлении (удаленно, без опыта). Вам прислать подробности по задачам?"

DETAILED_OFFER = f"""
Открыта удалённая позиция для кандидатов без опыта в криптовалютном направлении. В работе — обработка типовых заявок по пошаговой инструкции.

**Для начала обучения и связи с куратором напишите менеджеру:** {RECRUITER_TAG}
"""

# --- [ТРИГГЕРЫ] ---
KEYWORDS = ['ищу работу', 'нужна работа', 'подработку', 'ищу ворк', 'ищу удаленку', 'ищу вакансию']
STOP_WORDS = ['требуется', 'ищем', 'вакансия', 'набираю', 'зарплата']

DB_FILE = "sent_users.txt"
KNOWN_CHATS_FILE = "known_chats.txt" # Файл для отслеживания активных групп

# --- [ФУНКЦИИ] ---
def is_already_sent(user_id):
    if not os.path.exists(DB_FILE): return False
    with open(DB_FILE, "r") as f:
        return str(user_id) in f.read().splitlines()

def mark_as_sent(user_id):
    with open(DB_FILE, "a") as f:
        f.write(f"{user_id}\n")

def is_new_chat(chat_id):
    if not os.path.exists(KNOWN_CHATS_FILE): return True
    with open(KNOWN_CHATS_FILE, "r") as f:
        return str(chat_id) not in f.read().splitlines()

def mark_chat_known(chat_id):
    with open(KNOWN_CHATS_FILE, "a") as f:
        f.write(f"{chat_id}\n")

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# --- [ЛОГИКА] ---

@client.on(events.NewMessage)
async def group_handler(event):
    # ФИЛЬТР: Работаем ТОЛЬКО в группах (не в каналах)
    if not event.is_group:
        return

    # Подтверждение новой группы (сработает при первом сообщении в ней)
    if is_new_chat(event.chat_id):
        chat = await event.get_chat()
        mark_chat_known(event.chat_id)
        await client.send_message(REPORT_CHAT_ID, f"✅ **ГРУППА ПОДКЛЮЧЕНА:** «{chat.title}». Слушаю соискателей!")

    # Проверка актуальности и отправителя
    if (datetime.now(timezone.utc) - event.date).total_seconds() > 60: return
    if not event.sender or not isinstance(event.sender, types.User) or event.sender.bot: return
    
    text = event.raw_text.lower()
    if any(word in text for word in KEYWORDS) and not any(stop in text for stop in STOP_WORDS):
        sender = event.sender
        if not is_already_sent(sender.id):
            user_link = f"tg://user?id={sender.id}"
            chat = await event.get_chat()
            
            await client.send_message(REPORT_CHAT_ID, 
                f"🔎 **КАНДИДАТ:** {sender.first_name}\n📍 **Чат:** {chat.title}\n📝: _{event.raw_text}_\n👉 [ОТКРЫТЬ ЧАТ]({user_link})")
            
            # Пауза 5-15 минут
            await asyncio.sleep(random.randint(300, 900))
            
            try:
                await client.send_message(sender.id, FIRST_QUESTION)
                mark_as_sent(sender.id)
            except:
                await client.send_message(REPORT_CHAT_ID, f"❌ ЛС закрыты у `{sender.id}`")

@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def private_handler(event):
    if not event.sender or event.sender.bot: return
    text = event.raw_text.lower()
    positive_triggers = ['да', 'пришлите', 'интересно', 'подробности', 'расскажите', 'актуально']
    
    if is_already_sent(event.sender_id):
        if any(word in text for word in positive_triggers):
            await asyncio.sleep(random.randint(40, 80))
            await event.reply(DETAILED_OFFER)
            await client.send_message(REPORT_CHAT_ID, f"🔥 **ЛИД ЗАИНТЕРЕСОВАН!** ID: `{event.sender_id}`")

async def main():
    await client.start()
    print("🚀 Бот запущен. Работаем только в группах.")
    await client.run_until_disconnected()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
