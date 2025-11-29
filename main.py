import json
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.utils import exceptions
from aiogram import html
from aiogram import asyncio

API_TOKEN = "6909049704:AAGeTidLhxR7uQoHNlsz4IU9SoD8OW9PMpo"

FORBIDDEN_FILE = Path("forbidden_words.txt")
WARNINGS_FILE = Path("warnings.json")
STATS_FILE = Path("stats.json")

MAX_REACT_LEVEL = 50
AUTO_STATS_HOURS = [9, 14]  # Отправка статистики в 09:00 и 14:00 UTC

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Пользователи, которых бот игнорирует
IGNORED_USERS = [5470301151]

# Загружаем запрещённые слова
if FORBIDDEN_FILE.exists():
    BAD_WORDS = [w.strip().lower() for w in FORBIDDEN_FILE.read_text("utf-8").splitlines() if w.strip()]
else:
    BAD_WORDS = []
    log.warning("forbidden_words.txt не найден!")

# Загружаем предупреждения
if WARNINGS_FILE.exists():
    warnings_db = json.loads(WARNINGS_FILE.read_text("utf-8"))
else:
    warnings_db = {}

# Загружаем статистику
if STATS_FILE.exists():
    stats_db = json.loads(STATS_FILE.read_text("utf-8"))
else:
    stats_db = {"history": []}


def save_warnings():
    WARNINGS_FILE.write_text(json.dumps(warnings_db, ensure_ascii=False, indent=2), "utf-8")


def save_stats():
    STATS_FILE.write_text(json.dumps(stats_db, ensure_ascii=False, indent=2), "utf-8")


def log_warning(chat_id: int, user: types.User):
    stats_db["history"].append({
        "chat_id": chat_id,
        "user_id": user.id,
        "username": user.username or user.full_name,
        "timestamp": datetime.utcnow().isoformat()
    })
    save_stats()


def contains_bad_word(text: str):
    if text is None:
        return False
    text = text.lower()
    return any(bad in text for bad in BAD_WORDS)


def add_warning(chat_id: int, user: types.User):
    key = f"{chat_id}:{user.id}"
    count = warnings_db.get(key, 0) + 1
    warnings_db[key] = count
    save_warnings()
    log_warning(chat_id, user)
    return count


FUNNY_REACTS = [
    "Кажется, {mention} снова пытается выебнуться 😏",
    "{mention}, ну ты конечно даёшь 😂",
    "{mention}, твоя коллекция предупреждений растёт как на дрожжах 😅",
    "{mention}, осторожнее со словами пездюк 😇",
    "{mention}, так можно стать легендой этого чата 😎",
]


def generate_stats_report(chat_id: int) -> str:
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    daily = {}
    weekly = {}

    for event in stats_db["history"]:
        if event["chat_id"] != chat_id:
            continue
        ts = datetime.fromisoformat(event["timestamp"])
        name = event.get("username", f"User {event['user_id']}")

        if ts > day_ago:
            daily[name] = daily.get(name, 0) + 1
        if ts > week_ago:
            weekly[name] = weekly.get(name, 0) + 1

    def format_top(data):
        if not data:
            return "Нарушителей нет 🎉"
        sorted_users = sorted(data.items(), key=lambda x: x[1], reverse=True)
        lines = [f"👤 {name} → {count}" for name, count in sorted_users[:10]]
        return "\n".join(lines)

    return (
        "🏆 <b>Статистика нарушений</b>\n\n"
        "📅 <b>За последние 24 часа</b>:\n"
        f"{format_top(daily)}\n\n"
        "📈 <b>За последние 7 дней</b>:\n"
        f"{format_top(weekly)}"
    )


async def send_stats(bot: Bot, chat_id: int):
    try:
        report = generate_stats_report(chat_id)
        await bot.send_message(chat_id, report, parse_mode="HTML")
    except exceptions.TelegramBadRequest:
        log.error(f"Не удалось отправить статистику в чат {chat_id}")


async def auto_send_stats(bot: Bot, chat_id: int):
    while True:
        now = datetime.utcnow()
        for hour in AUTO_STATS_HOURS:
            send_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if now > send_time:
                send_time += timedelta(days=1)
            await asyncio.sleep((send_time - now).total_seconds())
            await send_stats(bot, chat_id)


async def handle_message(message: Message):
    user = message.from_user
    chat_id = message.chat.id

    # Игнорируем определённых пользователей
    if user.id in IGNORED_USERS:
        return

    text = message.text
    if contains_bad_word(text):
        try:
            await message.delete()
        except:
            pass

        count = add_warning(chat_id, user)
        mention = html.quote(user.full_name)

        if count % 5 == 0 and count <= MAX_REACT_LEVEL:
            reaction = random.choice(FUNNY_REACTS).format(mention=mention)
            reaction += f"\n\nВсего предупреждений: {count}"
            try:
                await message.answer(reaction, parse_mode="HTML")
            except exceptions.TelegramBadRequest:
                pass


async def chat_id_command(message: Message):
    chat_id = message.chat.id
    await message.reply(f"ID этого чата: <code>{chat_id}</code>", parse_mode="HTML")


async def main():
    bot = Bot(token=API_TOKEN, parse_mode="HTML")
    dp = Dispatcher()

    # Обработчики
    dp.message.register(handle_message, F.text)
    dp.message.register(chat_id_command, Command(commands=["chatid"]))

    # ID чата для автоотправки статистики
    CHAT_ID = -1003388389759  # <-- Вставьте сюда ID вашего канала или группы

    # Запуск автоотправки статистики
    asyncio.create_task(auto_send_stats(bot, CHAT_ID))

    # Запуск бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
