import asyncio
import random
import os
from datetime import datetime, timezone
from telethon import TelegramClient, events, types
from openai import AsyncOpenAI

# --- [КОНФИГУРАЦИЯ] ---
API_ID = 35523804          
API_HASH = 'ff7673ebc0e925a32fb52693bdfae16f'     
SESSION_NAME = 'hr_assistant_session'
REPORT_CHAT_ID = 7238685565 
RECRUITER_TAG = "@hannaober"

# Ключ OpenAI берем из настроек Railway (Variables)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

DB_FILE = "sent_users.txt"
KNOWN_CHATS_FILE = "known_chats.txt"

# Жесткие стоп-слова, чтобы отсекать работодателей без ИИ (экономия денег)
HARD_STOP_WORDS = [
    'требуется', 'ищем', 'вакансия', 'набираю', 'в команду', 'оплата от', 
    'зарплата', 'ищу сотрудника', 'ищу персонал', 'лс', 'пишите в директ'
]

# --- [ЛОГИКА ИИ] ---

async def ai_decision(text, mode="check_seeker"):
    """
    mode "check_seeker": Ищет ли человек работу (строго соискатель).
    mode "check_interest": Согласен ли человек на инфо (ответ на наше ЛС).
    """
    if mode == "check_seeker":
        system_msg = (
            "Ты — фильтр соискателей. Если сообщение — это ВАКАНСИЯ или ПРЕДЛОЖЕНИЕ работы (например: 'есть место', 'платим', 'требуется', 'ищем'), ответь только 'НЕТ'. "
            "Если человек сам ИЩЕТ работу (например: 'ищу ворк', 'нужна подработка', 'рассмотрю предложения'), ответь только 'ДА'. "
            "Будь очень строг. Объявления о найме от HR или компаний — это всегда 'НЕТ'."
        )
    else:
        system_msg = "Если человек проявил интерес к вакансии (сказал да, ок, пишите, что за работа, готов), ответь только 'ДА'. В остальных случаях 'НЕТ'."

    try:
        response = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": text}
            ],
            max_tokens=5,
            temperature=0
        )
        res = response.choices[0].message.content.strip().upper()
        return "ДА" in res
    except Exception as e:
        print(f"Ошибка ИИ: {e}")
        return False

# --- [ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ] ---

def check_user_sent(user_id):
    if not os.path.exists(DB_FILE): return False
    with open(DB_FILE, "r") as f: return str(user_id) in f.read().splitlines()

def save_user_sent(user_id):
    with open(DB_FILE, "a") as f: f.write(f"{user_id}\n")

# --- [ОСНОВНОЙ КЛИЕНТ] ---

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

@client.on(events.NewMessage)
async def handler(event):
    # 1. ОБРАБОТКА ГРУПП (ПОИСК)
    if event.is_group:
        if (datetime.now(timezone.utc) - event.date).total_seconds() > 60: return
        if not event.sender or event.sender.bot: return

        chat_id = str(event.chat_id)
        
        # Проверка нового чата
        if not os.path.exists(KNOWN_CHATS_FILE): open(KNOWN_CHATS_FILE, "w").close()
        with open(KNOWN_CHATS_FILE, "r+") as f:
            known = f.read().splitlines()
            if chat_id not in known:
                f.write(f"{chat_id}\n")
                chat = await event.get_chat()
                await client.send_message(REPORT_CHAT_ID, f"✅ **НОВЫЙ ЧАТ В РАБОТЕ:** {chat.title}")
                return

        text_lower = event.raw_text.lower()
        
        # ПРЕДВАРИТЕЛЬНЫЙ ФИЛЬТР: если есть стоп-слова, пропускаем без ИИ
        if any(stop in text_lower for stop in HARD_STOP_WORDS):
            return

        # ПРОВЕРКА ЧЕРЕЗ ИИ
        if await ai_decision(event.raw_text, mode="check_seeker"):
            if not check_user_sent(event.sender_id):
                user_link = f"tg://user?id={event.sender_id}"
                chat = await event.get_chat()
                
                await client.send_message(REPORT_CHAT_ID, 
                    f"🤖 **ИИ НАШЕЛ СОИСКАТЕЛЯ**\n👤: {event.sender.first_name}\n📍: {chat.title}\n📝: _{event.raw_text}_\n👉 [ОТКРЫТЬ ЧАТ]({user_link})")
                
                # Пауза имитации человека (5-10 минут)
                await asyncio.sleep(random.randint(300, 600))
                
                try:
                    welcome_msg = "Здравствуйте! Увидела ваше сообщение в группе. У нас сейчас открыта удаленная позиция (крипто-сфера, без опыта). Вам было бы интересно узнать детали?"
                    await client.send_message(event.sender_id, welcome_msg)
                    save_user_sent(event.sender_id)
                except:
                    await client.send_message(REPORT_CHAT_ID, f"❌ Закрыты ЛС у `{event.sender_id}`")

    # 2. ОБРАБОТКА ЛИЧКИ (ОТВЕТЫ)
    elif event.is_private:
        if not event.sender or event.sender.bot: return
        
        # Если мы этому человеку уже писали оффер
        if check_user_sent(event.sender_id):
            if await ai_decision(event.raw_text, mode="check_interest"):
                await asyncio.sleep(random.randint(40, 90))
                
                offer_details = (
                    f"Смотрите, работа простая: обработка заявок (обмен/конвертация) по инструкциям. "
                    f"Всему научим, график гибкий.\n\n"
                    f"Я помогаю с отбором, а всеми деталями и обучением занимается куратор. "
                    f"Напишите ему сейчас: {RECRUITER_TAG}\n"
                    f"Он ждет вашего сообщения!"
                )
                await event.reply(offer_details)
                await client.send_message(REPORT_CHAT_ID, f"🔥 **ЛИД ГОТОВ!** Кандидат [id:{event.sender_id}](tg://user?id={event.sender_id}) отправлен к {RECRUITER_TAG}")

async def main():
    await client.start()
    
    # ПРЕДЗАГРУЗКА: Записываем старые чаты в файл, чтобы не спамить при старте
    print("Синхронизация чатов...")
    current_ids = []
    async for dialog in client.iter_dialogs():
        if dialog.is_group:
            current_ids.append(str(dialog.id))
    
    with open(KNOWN_CHATS_FILE, "w") as f:
        f.write("\n".join(current_ids) + "\n")
        
    print("🚀 Бот Hanna Oberg (AI Edition) запущен!")
    await client.run_until_disconnected()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
