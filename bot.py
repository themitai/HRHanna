import asyncio
import random
import os
import logging
from datetime import datetime, timezone

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from openai import AsyncOpenAI

# ========================= КОНФИГУРАЦИЯ =========================
API_ID = 35523804
API_HASH = 'ff7673ebc0e925a32fb52693bdfae16f'
SESSION_NAME = 'hr_assistant_session'

REPORT_CHAT_ID = 7238685565
RECRUITER_TAG = "@hannaober"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

user_db = {}          # user_id -> status
dialog_owner = {}     # user_id -> True (бот начал диалог)

STOP_PHRASES = [
    'ищем', 'требуется', 'вакансия', 'набираем', 'предлагаем работу',
    'открыта вакансия', 'компания ищет', 'зп от', 'в офис', 'услуги', 'фнс'
]

def has_stop_phrase(text: str) -> bool:
    return any(phrase in text.lower() for phrase in STOP_PHRASES)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger(__name__)

async def ai_check(text: str, task: str = "is_seeker") -> bool:
    prompts = {
        "is_seeker": "Отвечай ТОЛЬКО ДА или НЕТ. ДА — только если человек явно ищет работу.",
        "is_interested": "Человек проявил интерес к вакансии? да, давай, интересно, расскажи, хочу, ок — это ДА. Отвечай ТОЛЬКО ДА или НЕТ."
    }
    try:
        res = await ai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompts[task]}, {"role": "user", "content": text}],
            max_tokens=8,
            temperature=0
        )
        return "ДА" in res.choices[0].message.content.upper()
    except Exception as e:
        log.error(f"OpenAI ошибка: {e}")
        return False


client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


@client.on(events.NewMessage)
async def handler(event):
    if not event.sender or getattr(event.sender, 'bot', False):
        return

    user_id = event.sender_id
    text = event.raw_text.strip()

    # ====================== ЛИЧНЫЕ СООБЩЕНИЯ ======================
    is_private = (
        getattr(event, 'is_private', False) or
        event.chat_id == user_id or
        (getattr(event, 'to_id', None) and hasattr(event.to_id, 'user_id') and event.to_id.user_id == user_id)
    )

    if is_private:
        status = user_db.get(user_id)
        owner = dialog_owner.get(user_id, False)

        log.info(f"[ЛИЧКА] От {user_id} | статус={status} | owner_бот={owner} | текст=\"{text}\"")

        # Если диалог начал НЕ бот — всё равно пытаемся продолжить, если есть статус
        if status:
            try:
                if await ai_check(text, "is_interested"):
                    log.info(f"[ЛИЧКА] ИИ: интерес подтверждён от {user_id}")

                    if status == "sent":
                        await event.reply(
                            "Условия: удаленно, крипто-направление. ЗП: 2000€ + 2%. Обучение 2 дня. Подходит?"
                        )
                        user_db[user_id] = "offered"
                        log.info(f"[ЛИЧКА] Отправили условия → {user_id}")

                    elif status == "offered":
                        await event.reply(f"Супер! Пиши куратору Ханне: {RECRUITER_TAG}")
                        user_db[user_id] = "final"
                        await client.send_message(
                            REPORT_CHAT_ID,
                            f"🔥 **ЛИД ДОЖАТ:** @{event.sender.username or user_id}"
                        )
                        log.info(f"[ЛИЧКА] ЛИД ДОЖАТ → {user_id}")
                else:
                    log.info(f"[ЛИЧКА] ИИ: интерес НЕ подтверждён от {user_id}")
            except Exception as e:
                log.error(f"Ошибка в личке {user_id}: {e}")
        else:
            log.info(f"[ЛИЧКА] Нет статуса для {user_id} — игнорируем")
        return

    # ====================== ГРУППЫ ======================
    if not event.is_group:
        return
    if (datetime.now(timezone.utc) - event.date).total_seconds() > 120:
        return
    if has_stop_phrase(text):
        return

    if await ai_check(text, "is_seeker"):
        if user_id not in user_db:
            try:
                chat = await event.get_chat()
                msg_link = f"https://t.me/{chat.username}/{event.id}" if getattr(chat, 'username', None) \
                    else f"https://t.me/c/{str(event.chat_id)[4:]}/{event.id}"

                report = (
                    f"🎯 **ЛИД НАЙДЕН**\n"
                    f"👤 **Имя:** {event.sender.first_name or '—'}\n"
                    f"🆔 **ID:** `{user_id}`\n"
                    f"💬 **Текст:** {text[:120]}\n"
                    f"📍 **Группа:** {chat.title}\n"
                    f"🔗 [Ссылка]({msg_link})"
                )
                await client.send_message(REPORT_CHAT_ID, report, link_preview=False)

                user_db[user_id] = "sent"
                dialog_owner[user_id] = True   # помечаем, что бот начал диалог

                await asyncio.sleep(random.randint(15, 35))

                await client.send_message(
                    user_id,
                    "Здравствуйте! Увидела ваш запрос в группе. "
                    "У нас открыта удаленная позиция (крипто-сфера, без опыта). "
                    "Вам интересно узнать детали?"
                )
                log.info(f"✅ Бот отправил первое сообщение → {user_id}")

            except FloodWaitError as e:
                log.warning(f"FloodWait {e.seconds} сек")
                await asyncio.sleep(e.seconds + 5)
            except Exception as e:
                log.error(f"Ошибка отправки лиду {user_id}: {e}")


async def main():
    await client.start()
    log.info("🚀 БОТ ЗАПУЩЕН — режим 'бот ведёт диалог' + поддержка когда HR пишет первой")
    await client.run_until_disconnected()


if __name__ == '__main__':
    asyncio.run(main())
