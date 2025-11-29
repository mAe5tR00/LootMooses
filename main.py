import json
import logging
import random
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
import asyncio

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ChatMemberUpdated
from aiogram.exceptions import TelegramBadRequest

API_TOKEN = "6909049704:AAGeTidLhxR7uQoHNlsz4IU9SoD8OW9PMpo"

FORBIDDEN_FILE = Path("forbidden_words.txt")
WARNINGS_FILE = Path("warnings.json")
STATS_FILE = Path("stats.json")

MAX_REACT_LEVEL = 50

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Пользователи, которых бот игнорирует
IGNORED_USERS = [5470301151]

# Загрузка запрещённых слов
if FORBIDDEN_FILE.exists():
    BAD_WORDS = [w.strip().lower() for w in FORBIDDEN_FILE.read_text("utf-8").splitlines() if w.strip()]
else:
    BAD_WORDS = []
    log.warning("forbidden_words.txt не найден!")

# Загрузка предупреждений
if WARNINGS_FILE.exists():
    warnings_db = json.loads(WARNINGS_FILE.read_text("utf-8"))
else:
    warnings_db = {}

# Загрузка статистики
if STATS_FILE.exists():
    stats_db = json.loads(STATS_FILE.read_text("utf-8"))
else:
    stats_db = {"history": []}

def save_warnings():
    WARNINGS_FILE.write_text(json.dumps(warnings_db, ensure_ascii=False, indent=2), "utf-8")

def save_stats():
    STATS_FILE.write_text(json.dumps(stats_db, ensure_ascii=False, indent=2), "utf-8")

def log_warning(chat_id, user_id, username):
    stats_db["history"].append({
        "chat_id": chat_id,
        "user_id": user_id,
        "username": username,
        "timestamp": datetime.utcnow().isoformat()
    })
    save_stats()

def contains_bad_word(text: str):
    if not text:
        return False
    text = text.lower()
    return any(bad in text for bad in BAD_WORDS)

def add_warning(chat_id, user_id, username):
    key = f"{chat_id}:{user_id}"
    count = warnings_db.get(key, 0) + 1
    warnings_db[key] = count
    save_warnings()
    log_warning(chat_id, user_id, username)
    return count

FUNNY_REACTS = [
    "Кажется, {mention} снова пытается выебнуться 😏",
    "{mention}, ну ты конечно даёшь 😂",
    "{mention}, твоя коллекция предупреждений растёт как на дрожжах 😅",
    "{mention}, осторожнее со словами пездюк 😇",
    "{mention}, так можно стать легендой этого чата 😎",
]

def generate_stats_report(chat_id):
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    daily = {}
    weekly = {}

    for event in stats_db["history"]:
        if event["chat_id"] != chat_id:
            continue

        ts = datetime.fromisoformat(event["timestamp"])
        username = event.get("username") or str(event["user_id"])

        if ts > day_ago:
            daily[username] = daily.get(username, 0) + 1

        if ts > week_ago:
            weekly[username] = weekly.get(username, 0) + 1

    def format_top(data):
        if not data:
            return "Нарушителей нет 🎉"
        sorted_users = sorted(data.items(), key=lambda x: x[1], reverse=True)
        lines = []
        for uname, count in sorted_users[:10]:
            lines.append(f"👤 {uname} → {count}")
        return "\n".join(lines)

    return (
        "🏆 <b>Статистика нарушений</b>\n\n"
        "📅 <b>За последние 24 часа</b>:\n"
        f"{format_top(daily)}\n\n"
        "📈 <b>За последние 7 дней</b>:\n"
        f"{format_top(weekly)}"
    )

async def send_stats(bot: Bot, chat_id: int):
    report = generate_stats_report(chat_id)
    try:
        await bot.send_message(chat_id, report, parse_mode="HTML")
    except TelegramBadRequest as e:
        log.error(f"Ошибка при отправке статистики: {e}")

# --------------------------- Обработка сообщений ---------------------------

async def handle_message(message: Message):
    if not message.text or message.from_user.id in IGNORED_USERS:
        return

    user = message.from_user
    chat_id = message.chat.id
    username = user.username or f"@{user.first_name}"

    if contains_bad_word(message.text):
        # Удаляем сообщение
        try:
            await message.delete()
        except TelegramBadRequest:
            pass

        count = add_warning(chat_id, user.id, username)
        if count % 5 == 0 and count <= MAX_REACT_LEVEL:
            reaction = random.choice(FUNNY_REACTS).format(mention=username)
            reaction += f"\n\nВсего предупреждений: {count}"
            await message.answer(reaction)

# --------------------------- Команды ---------------------------

async def chatid_command(message: Message):
    await message.reply(f"ID этого чата: {message.chat.id}")

# --------------------------- Старт и автоотправка ---------------------------

async def scheduler(bot: Bot, chat_id: int):
    while True:
        now = datetime.now()
        # Отправляем в 14:00 и 19:00 по местному времени
        for target_hour in [14, 19]:
            target = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
            if now > target:
                target += timedelta(days=1)
            await asyncio.sleep((target - now).total_seconds())
            await send_stats(bot, chat_id)
        await asyncio.sleep(60)  # небольшая задержка чтобы не перегружать цикл

async def main():
    bot = Bot(token=API_TOKEN)
    dp = Dispatcher()

    dp.startup.register(lambda _: log.info("Бот запущен"))
    dp.message.register(handle_message, F.text & ~F.command)
    dp.message.register(chatid_command, Command(commands=["chatid"]))

    # Укажи свой канал или чат, куда будет отправляться статистика
    chat_id_for_stats = -1003388389759

    # Запуск планировщика
    asyncio.create_task(scheduler(bot, chat_id_for_stats))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
