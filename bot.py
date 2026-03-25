import asyncio
import random
import os
from datetime import datetime, timezone
from telethon import TelegramClient, events, types
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors.rpcerrorlist import PeerIdInvalidError

# --- [БЛОК НАСТРОЕК] ---
# ЗАМЕНИ НА СВОИ API ДАННЫЕ С GitHub
API_ID = 35523804          
API_HASH = 'ff7673ebc0e925a32fb52693bdfae16f'     
SESSION_NAME = 'hr_assistant_session'

# Твой ID для отчетов
REPORT_CHAT_ID = 7238685565 

# Контакт рекрутера
RECRUITER_TAG = "@hannaober" 

# --- [ТЕКСТЫ] ---
FIRST_QUESTION = "Здравствуйте! Увидела ваш запрос в группе по поиску работы. У нас сейчас открыта позиция в криптовалютном направлении (удаленно, без опыта). Вам прислать подробности по задачам?"

# (Я использую тот же текст, что ты присылал ранее)
DETAILED_OFFER = f"""
Открыта удалённая позиция для кандидатов без опыта в криптовалютном направлении. В работе — обработка типовых заявок внутри процесса команды.

**Что вы будете делать:**
* Получать заявки в рабочем канале и брать их в работу.
* Проверять наличие вводных данных.
* Выполнять операции по регламенту (перевод/конвертация).
* Доводить заявку до результата.

**Обучение:**
Сначала — вводное обучение. Далее — практика с наставником.

**Для начала обучения и связи с куратором напишите менеджеру:** {RECRUITER_TAG}
"""

# --- [ТРИГГЕРЫ] ---
KEYWORDS = [
    'ищу работу', 'ищу подработку', 'нужна работа', 'ищу вакансию', 
    'рассмотрю предложения', 'ищу удаленку', 'ищу удаленную', 
    'где найти работу', 'ищу работу без опыта', 'ищу заработок', 
    'хочу работать', 'ищу ворк', 'нужен ворк', 'ищу профит'
]

STOP_WORDS = [
    'требуется', 'ищем', 'вакансия', 'набираю', 'в команду', 
    'платим', 'зарплата', 'оплата', 'лс', 'пишите', 'подробности в',
    'обучаем', 'набор', 'ищу сотрудника', 'ищу персонал', 'ищу людей'
]

DB_FILE = "sent_users.txt"
GROUPS_FILE = "groups.txt"

# --- [ФУНКЦИИ] ---
def is_already_sent(user_id):
    if not os.path.exists(DB_FILE): return False
    with open(DB_FILE, "r") as f:
        return str(user_id) in f.read().splitlines()

def mark_as_sent(user_id):
    with open(DB_FILE, "a") as f:
        f.write(f"{user_id}\n")

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# --- [ОСНОВНАЯ ЛОГИКА] ---

# 1. МОНИТОРИНГ ГРУПП + ОТЧЕТ
@client.on(events.NewMessage)
async def group_handler(event):
    if event.is_group:
        # Проверка даты (не старое)
        if (datetime.now(timezone.utc) - event.date).total_seconds() > 60:
            return

        # Проверка на человека и не бота
        if not event.sender or not isinstance(event.sender, types.User) or event.sender.bot:
            return
        
        text = event.raw_text.lower()
        if len(text) > 250: return 
        
        if any(word in text for word in KEYWORDS) and not any(stop in text for stop in STOP_WORDS):
            sender = event.sender
            chat = await event.get_chat()
            
            if not is_already_sent(sender.id):
                username = f"@{sender.username}" if sender.username else "Нет юзернейма"
                user_link = f"tg://user?id={sender.id}"
                
                report_msg = (
                    f"🎯 **НАЙДЕН КАНДИДАТ**\n"
                    f"👤 **Имя:** {sender.first_name} {sender.last_name or ''}\n"
                    f"🆔 **ID:** `{sender.id}`\n"
                    f"🔗 **Username:** {username}\n"
                    f"📍 **Группа:** {chat.title}\n"
                    f"📝 **Сообщение:** __{event.raw_text}__\n\n"
                    f"👉 [ОТКРЫТЬ ЧАТ С НИМ]({user_link})"
                )
                
                await client.send_message(REPORT_CHAT_ID, report_msg)
                
                # --- [ИСПРАВЛЕНИЕ: УВЕЛИЧЕННАЯ ПАУЗА] ---
                # Ждем от 3 до 10 минут, чтобы Telegram не банил за спам.
                wait_time = random.randint(200, 600) 
                print(f"🎯 Нашла кандидата {sender.id}. Жду {wait_time}с для имитации человека...")
                await asyncio.sleep(wait_time)
                
                try:
                    await client.send_message(sender.id, FIRST_QUESTION)
                    mark_as_sent(sender.id)
                    print(f"✅ Оффер отправлен {sender.id}")
                except Exception as e:
                    await client.send_message(REPORT_CHAT_ID, f"❌ Не удалось написать `{sender.id}` (ЛС закрыты)\n👉 Попробуйте [написать вручную]({user_link})")

# 2. АВТООТВЕТЧИК В ЛИЧКЕ
@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def private_handler(event):
    if not event.sender or not isinstance(event.sender, types.User) or event.sender.bot:
        return
        
    text = event.raw_text.lower()
    positive_triggers = ['да', 'пришлите', 'интересно', 'подробности', 'расскажите', 'актуально', 'что за работа', 'хорошо', 'давайте']
    
    # --- [ИСПРАВЛЕНИЕ: УБРАНА ЖЕСТКАЯ ПРОВЕРКА SENDER_ID] ---
    # Мы отвечаем всем, кто ответил "Да", при условии, что мы писали им первыми.
    if is_already_sent(event.sender_id):
        if any(word in text for word in positive_triggers):
            
            # --- [ИСПРАВЛЕНИЕ: ПАУЗА ДЛЯ ИМИТАЦИИ ПЕЧАТИ] ---
            # Ждем от 30 до 90 секунд перед отправкой большого текста
            await asyncio.sleep(random.randint(30, 90))
            await event.reply(DETAILED_OFFER)
            
            # Отчет тебе
            await client.send_message(REPORT_CHAT_ID, f"🔥 **ЛИД ЗАИНТЕРЕСОВАН!**\nКандидат [id:{event.sender_id}](tg://user?id={event.sender_id}) ответил: __{event.raw_text}__")

# --- [ФУНКЦИЯ ВСТУПЛЕНИЯ С ОТЧЕТОМ] ---
async def join_groups():
    if not os.path.exists(GROUPS_FILE): return
    with open(GROUPS_FILE, "r") as f:
        groups = [line.strip() for line in f if line.strip()]

    for group in groups:
        try:
            await client(JoinChannelRequest(group))
            await client.send_message(REPORT_CHAT_ID, f"🌐 **ВСТУПЛЕНИЕ:** Зашла в {group}")
            # Пауза между группами
            await asyncio.sleep(random.randint(400, 900))
        except Exception as e:
            # Игнорируем ошибку, если аккаунт уже состоит в группе
            if "USER_ALREADY_PARTICIPANT" in str(e): return
            await client.send_message(REPORT_CHAT_ID, f"❌ **ОШИБКА ВСТУПЛЕНИЯ:** {group}\n{e}")

async def main():
    await client.start()
    print(f"🤖 Бот Hanna Oberg запущен. Отчеты идут в чат ID: {REPORT_CHAT_ID}")
    asyncio.create_task(join_groups())
    await client.run_until_disconnected()

if __name__ == '__main__':
    # Fix for DeprecationWarning in Python 3.10+
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
