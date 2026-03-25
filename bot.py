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

# Текст подробного описания вакансии
VACANCY_DETAILS = (
    "Открыта удалённая позиция (без опыта) в крипто-направлении. "
    "Суть: обработка заявок (перевод/конвертация) по пошаговой инструкции. "
    "Обучение на старте с наставником.\n\n"
    "💰 **Оплата:** 2000€ в месяц + 2% от объема.\n"
    "📍 **Формат:** Удаленно, гибкий график.\n\n"
    "Вам подходит такой формат? Рассказать, как связаться с куратором?"
)

# --- [СТРОГАЯ ЛОГИКА АНАЛИЗА] ---

async def ai_evaluate_lead(text):
    # 1. Технический фильтр: Вакансии обычно длинные и с кучей галочек
    bad_icons = ['✅', '🟢', '🟩', '📍', '💰', '⏰']
    icon_count = sum(text.count(icon) for icon in bad_icons)
    
    if len(text) > 100 or icon_count > 3:
        return {"aim": False, "score": 0, "reason": "Похоже на оформленную вакансию (слишком много эмодзи или текста)"}

    # 2. Запрос к ИИ
    system_prompt = (
        "Ты — эксперт-рекрутер. Твоя задача: отличить СОИСКАТЕЛЯ от РАБОТОДАТЕЛЯ. "
        "ОТВЕТЬ aim: false, ЕСЛИ: в тексте есть условия работы, требования ('нужен опыт', 'знание языка'), "
        "описание компании или призыв 'пишите нам'. "
        "ОТВЕТЬ aim: true, ТОЛЬКО ЕСЛИ: человек пишет от СЕБЯ: 'Ищу работу', 'Нужна подработка', 'Хочу ворк'. "
        "Верни JSON: {'aim': boolean, 'score': 0-100, 'reason': 'почему такое решение'}"
    )
    
    try:
        response = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": text}],
            response_format={ "type": "json_object" }
        )
        res = json.loads(response.choices[0].message.content)
        # Если ИИ сомневается (низкий score), отсекаем
        if res.get("score", 0) < 75:
            res["aim"] = False
        return res
    except:
        return {"aim": False, "score": 0, "reason": "Ошибка ИИ"}

# --- [РАБОТА С БАЗОЙ СТАТУСОВ] ---

def get_status(user_id):
    if not os.path.exists(DB_FILE): return None
    with open(DB_FILE, "r") as f:
        for line in f:
            if line.startswith(f"{user_id}:"):
                return line.split(":")[-1].strip()
    return None

def set_status(user_id, status):
    lines = []
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            lines = [l for l in f.readlines() if not l.startswith(f"{user_id}:")]
    lines.append(f"{user_id}:{status}\n")
    with open(DB_FILE, "w") as f:
        f.writelines(lines)

# --- [ОСНОВНОЙ КЛИЕНТ] ---

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

@client.on(events.NewMessage)
async def handler(event):
    if not event.sender or event.sender.bot: return

    # А) ГРУППЫ (ПОИСК ЛИДОВ)
    if event.is_group:
        if (datetime.now(timezone.utc) - event.date).total_seconds() > 60: return
        
        analysis = await ai_evaluate_lead(event.raw_text)
        
        if analysis.get("aim") is True:
            if get_status(event.sender_id) is None:
                chat = await event.get_chat()
                sender = event.sender
                
                # Формируем ссылку на сообщение
                if chat.username:
                    msg_link = f"https://t.me/{chat.username}/{event.id}"
                else:
                    msg_link = f"https://t.me/c/{str(event.chat_id)[4:]}/{event.id}"

                # Красивый отчет
                report = (
                    f"🎯 **score: {analysis.get('score')}%**\n"
                    f"✅ **aim: true**\n"
                    f"----------- \n"
                    f"**question:** \n{event.raw_text} \n"
                    f"----------- \n"
                    f"**sender:** @{sender.username if sender.username else 'none'} ({sender.first_name})\n"
                    f"**group:** {chat.title} (`{event.chat_id}`)\n"
                    f"**reason:** {analysis.get('reason')}\n"
                    f"**message_link:** [ПЕРЕЙТИ]({msg_link})"
                )
                
                await client.send_message(REPORT_CHAT_ID, report, link_preview=False)
                
                # Пишем соискателю в ЛС
                await asyncio.sleep(random.randint(30, 60))
                try:
                    await client.send_message(event.sender_id, "Здравствуйте! Увидела ваш запрос в группе. У нас сейчас открыта удаленная позиция (крипто-сфера, без опыта). Вам было бы интересно узнать детали?")
                    set_status(event.sender_id, "sent")
                except Exception as e:
                    await client.send_message(REPORT_CHAT_ID, f"⚠️ Не удалось написать в ЛС `{event.sender_id}` (закрыто).")

    # Б) ЛИЧКА (ВЕДЕНИЕ ПО ВОРОНКЕ)
    elif event.is_private:
        status = get_status(event.sender_id)
        if not status: return

        # Шаг 1: Ответ на приветствие
        if status == "sent":
            # Простой ИИ чек на интерес
            response = await ai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": "Если человек проявил интерес к работе, ответь ДА."}, {"role": "user", "content": event.raw_text}]
            )
            if "ДА" in response.choices[0].message.content.upper():
                await asyncio.sleep(random.randint(10, 20))
                await event.reply(VACANCY_DETAILS)
                set_status(event.sender_id, "offered")

        # Шаг 2: Ответ на вакансию
        elif status == "offered":
            response = await ai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": "Если человек согласен на работу или хочет контакты, ответь ДА."}, {"role": "user", "content": event.raw_text}]
            )
            if "ДА" in response.choices[0].message.content.upper():
                await asyncio.sleep(random.randint(10, 20))
                await event.reply(f"Отлично! Напишите нашему куратору Ханне: {RECRUITER_TAG}\nОна введет вас в курс дела!")
                set_status(event.sender_id, "final")
                await client.send_message(REPORT_CHAT_ID, f"🔥 **ЛИД ГОТОВ!** Кандидат @{event.sender.username if event.sender.username else event.sender_id} пошел к Ханне.")

async def main():
    await client.start()
    print("🚀 Бот запущен! Ищу соискателей с максимальной строгостью.")
    await client.run_until_disconnected()

if __name__ == '__main__':
    client.loop.run_until_complete(main())
