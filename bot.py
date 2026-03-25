import asyncio
import random
import os
import json
from datetime import datetime, timezone
from telethon import TelegramClient, events, types
from openai import AsyncOpenAI

# --- [КОНФИГУРАЦИЯ] ---
API_ID = 35523804          
API_HASH = 'ff7673ebc0e925a32fb52693bdfae16f'     
SESSION_NAME = 'hr_assistant_session'
REPORT_CHAT_ID = 7238685565 
RECRUITER_TAG = "@hannaober"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

DB_FILE = "sent_users.txt"
KNOWN_CHATS_FILE = "known_chats.txt"

# --- [ЛОГИКА ИИ С ОЦЕНКОЙ] ---

async def ai_evaluate_lead(text):
    """Возвращает JSON с оценкой и решением"""
    system_prompt = (
        "Ты — опытный рекрутер. Проанализируй сообщение соискателя. "
        "Верни ответ СТРОГО в формате JSON: "
        '{"aim": true/false, "score": 0-100, "reason": "кратко"}. '
        "aim=true если человек ищет работу. score выше, если запрос четкий (город, вакансия)."
    )
    try:
        response = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text}],
            response_format={ "type": "json_object" }
        )
        return json.loads(response.choices[0].message.content)
    except:
        return {"aim": False, "score": 0, "reason": "error"}

# --- [БАЗА ДАННЫХ] ---

def get_user_status(user_id):
    if not os.path.exists(DB_FILE): return None
    with open(DB_FILE, "r") as f:
        for line in f:
            if str(user_id) in line: return line.split(":")[-1].strip()
    return None

def update_user_status(user_id, status):
    lines = []
    found = False
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            lines = [l for l in f.readlines() if str(user_id) not in l]
    lines.append(f"{user_id}:{status}\n")
    with open(DB_FILE, "w") as f: f.writelines(lines)

# --- [КЛИЕНТ] ---

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

@client.on(events.NewMessage)
async def handler(event):
    if not event.sender or event.sender.bot: return

    # А) ОБРАБОТКА ГРУПП
    if event.is_group:
        if (datetime.now(timezone.utc) - event.date).total_seconds() > 60: return
        
        # Запуск анализа ИИ
        analysis = await ai_evaluate_lead(event.raw_text)
        
        if analysis.get("aim") and analysis.get("score", 0) > 50:
            if get_user_status(event.sender_id) is None:
                # Сбор данных для отчета
                chat = await event.get_chat()
                sender = event.sender
                msg_link = f"https://t.me/c/{str(event.chat_id)[4:]}/{event.id}" if event.is_channel else f"https://t.me/{chat.username}/{event.id}" if chat.username else "no link"
                
                report = (
                    f"🎯 **score: {analysis['score']}%**\n"
                    f"✅ **aim: {str(analysis['aim']).lower()}**\n"
                    f"----------- \n"
                    f"**question:** \n{event.raw_text} \n"
                    f"----------- \n"
                    f"**sender_username:** @{sender.username if sender.username else 'none'}\n"
                    f"**sender_fullName:** {sender.first_name} {sender.last_name if sender.last_name else ''}\n"
                    f"**group:** {chat.title} ({event.chat_id})\n"
                    f"**sender_id:** `{event.sender_id}`\n"
                    f"**message_link:** [ПЕРЕЙТИ]({msg_link})"
                )
                
                await client.send_message(REPORT_CHAT_ID, report, link_preview=False)
                
                # Отправка в ЛС (имитация)
                await asyncio.sleep(random.randint(20, 40))
                try:
                    await client.send_message(event.sender_id, "Здравствуйте! Увидела ваш запрос в группе. У нас есть удаленная вакансия в крипто-сфере, обучение с нуля. Вам было бы интересно?")
                    update_user_status(event.sender_id, "sent")
                except:
                    await client.send_message(REPORT_CHAT_ID, "⚠️ ЛС закрыты, не смог написать.")

    # Б) ЛИЧКА (ВОРОНКА)
    elif event.is_private:
        status = get_user_status(event.sender_id)
        if not status: return

        if status == "sent":
            # Проверка интереса через простой AI-чек
            await asyncio.sleep(5)
            await event.reply("Суть работы: обработка заявок (удаленно). ЗП: 2000€ + 2%. Подходит?")
            update_user_status(event.sender_id, "offered")
        
        elif status == "offered":
            await asyncio.sleep(5)
            await event.reply(f"Отлично! Напишите куратору: {RECRUITER_TAG}")
            update_user_status(event.sender_id, "final")
            await client.send_message(REPORT_CHAT_ID, f"🔥 **ЛИД ДОЖАТ!** @{event.sender.username if event.sender.username else event.sender_id}")

async def main():
    await client.start()
    print("🤖 Бот запущен с расширенной аналитикой!")
    await client.run_until_disconnected()

if __name__ == '__main__':
    client.loop.run_until_complete(main())
