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
RECRUITER_TAG = "@hannaober" # Тег, куда ИИ будет отправлять людей

# ИИ Ключ подтягивается из переменных Railway
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

DB_FILE = "sent_users.txt"
KNOWN_CHATS_FILE = "known_chats.txt"

# --- [ЛОГИКА ИИ] ---

async def ai_decision(text, system_prompt):
    try:
        response = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            max_tokens=10,
            temperature=0
        )
        res = response.choices[0].message.content.strip().upper()
        return "ДА" in res
    except Exception as e:
        print(f"Ошибка ИИ: {e}")
        return False

# --- [ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ] ---

def check_user(user_id):
    if not os.path.exists(DB_FILE): return False
    with open(DB_FILE, "r") as f: return str(user_id) in f.read().splitlines()

def save_user(user_id):
    with open(DB_FILE, "a") as f: f.write(f"{user_id}\n")

# --- [ОСНОВНОЙ КЛИЕНТ] ---

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

@client.on(events.NewMessage)
async def handler(event):
    # 1. Если это группа - ищем соискателей
    if event.is_group:
        if (datetime.now(timezone.utc) - event.date).total_seconds() > 60: return
        if not event.sender or event.sender.bot: return

        # Логируем новую группу
        if not os.path.exists(KNOWN_CHATS_FILE): open(KNOWN_CHATS_FILE, "w").close()
        with open(KNOWN_CHATS_FILE, "r+") as f:
            if str(event.chat_id) not in f.read().splitlines():
                f.write(f"{event.chat_id}\n")
                chat = await event.get_chat()
                await client.send_message(REPORT_CHAT_ID, f"✅ **ГРУППА В РАБОТЕ:** {chat.title}")

        # Проверка сообщения через ИИ
        prompt = "Ты HR. Если человек пишет, что ищет работу, подработку или нуждается в деньгах/ворке, ответь только 'ДА'. Если это спам, услуги или вакансия — 'НЕТ'."
        if await ai_decision(event.raw_text, prompt):
            if not check_user(event.sender_id):
                user_link = f"tg://user?id={event.sender_id}"
                await client.send_message(REPORT_CHAT_ID, f"🤖 **ИИ НАШЕЛ ЛИДА**\n👤: {event.sender.first_name}\n📝: _{event.raw_text}_\n👉 [ОТКРЫТЬ ЧАТ]({user_link})")
                
                await asyncio.sleep(random.randint(300, 600))
                try:
                    await client.send_message(event.sender_id, "Здравствуйте! Увидела ваше сообщение в группе. У нас есть вакансия на удаленку (крипто-сфера, без опыта). Вам было бы интересно узнать детали?")
                    save_user(event.sender_id)
                except:
                    await client.send_message(REPORT_CHAT_ID, f"❌ ЛС закрыты у `{event.sender_id}`")

    # 2. Если это личка - обрабатываем интерес
    elif event.is_private:
        if not event.sender or event.sender.bot: return
        
        prompt = "Если человек ответил согласием, проявил интерес или задал уточняющий вопрос по вакансии (да, расскажите, что за работа), ответь только 'ДА'. В остальных случаях 'НЕТ'."
        if check_user(event.sender_id) and await ai_decision(event.raw_text, prompt):
            await asyncio.sleep(random.randint(40, 80))
            
            # Текст с логичным переводом на рекрутера
            response = (
                f"Смотрите, работа заключается в обработке заявок (обмен/конвертация) по четким инструкциям. "
                f"График свободный, обучение бесплатное.\n\n"
                f"Я всего лишь помогаю с первичным отбором. Чтобы обсудить детали и начать обучение, "
                f"напишите, пожалуйста, нашему куратору: {RECRUITER_TAG}\n"
                f"Он сейчас на связи и введет вас в курс дела!"
            )
            await event.reply(response)
            await client.send_message(REPORT_CHAT_ID, f"🔥 **ЛИД СОЗРЕЛ!** Кандидат [id:{event.sender_id}](tg://user?id={event.sender_id}) отправлен к куратору.")

async def main():
    await client.start()
    print("🚀 Бот с ИИ OpenAI запущен и готов к работе!")
    await client.run_until_disconnected()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
