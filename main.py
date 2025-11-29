import json
import logging
import random
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ChatMemberUpdated
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.bot import DefaultBotProperties
from aiogram.filters import Command
from aiogram.utils.exceptions import TelegramBadRequest

API_TOKEN = "6909049704:AAGeTidLhxR7uQoHNlsz4IU9SoD8OW9PMpo"  # вставь свой токен

FORBIDDEN_FILE = Path("forbidden_words.txt")
WARNINGS_FILE = Path("warnings.json")
STATS_FILE = Path("stats.json")
CHAT_ID = -1003388389759  # вставь ID своего чата

MAX_REACT_LEVEL = 50
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

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

def log_warning(user_id: int):
    stats_db["history"].append({
        "user_id": user_id,
        "timestamp": datetime.utcnow().isoformat()
    })
    save_stats()

def contains_bad_word(text: str):
    if not text:
        return False
    text = text.lower()
    return any(bad in text for bad in BAD_WORDS)

def add_warning(user_id: int):
    count = warnings_db.get(str(user_id), 0) + 1
    warnings_db[str(user_id)] = count
    save_warnings()
    log_warning(user_id)
    return count

FUNNY_REACTS = [
    "Кажется, {mention} снова пытается выебнуться 😏",
    "{mention}, ну ты конечно даёшь 😂",
    "{mention}, твоя коллекция предупреждений растёт как на дрожжах 😅",
    "{mention}, осторожнее со словами пездюк 😇",
    "{mention}, так можно стать легендой этого чата 😎",
]

def generate_stats_report():
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    daily = {}
    weekly = {}

    for event in stats_db["history"]:
        ts = datetime.fromisoformat(event["timestamp"])
        user_id = event["user_id"]

        if ts > day_ago:
            daily[user_id] = daily.get(user_id, 0) + 1
        if ts > week_ago:
            weekly[user_id] = weekly.get(user_id, 0) + 1

    def format_top(data):
        if not data:
            return "Нарушителей нет 🎉"
        sorted_users = sorted(data.items(), key=lambda x: x[1], reverse=True)
        lines = []
        for uid, count in sorted_users[:10]:
            # Подставляем никнейм, если есть
            user = dp.bot.get_chat(uid)
            mention = f"@{user.username}" if user and user.username else str(uid)
            lines.append(f"👤 {mention} → {count}")
        return "\n".join(lines)

    return (
        "🏆 <b>Статистика нарушений</b>\n\n"
        "📅 <b>За последние 24 часа</b>:\n"
        f"{format_top(daily)}\n\n"
        "📈 <b>За последние 7 дней</b>:\n"
        f"{format_top(weekly)}"
    )

async def send_stats():
    try:
        report = generate_stats_report()
        await bot.send_message(CHAT_ID, report)
    except TelegramBadRequest as e:
        log.error(f"Ошибка при отправке статистики: {e}")

# -------------------- Обработчики --------------------
async def handle_message(message: Message):
    if not message.text:
        return
    if message.from_user.id in IGNORED_USERS:
        return
    if contains_bad_word(message.text):
        try:
            await message.delete()
        except TelegramBadRequest:
            pass

        count = add_warning(message.from_user.id)
        mention = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
        if count % 5 == 0 and count <= MAX_REACT_LEVEL:
            reaction = random.choice(FUNNY_REACTS).format(mention=mention)
            reaction += f"\n\nВсего предупреждений: {count}"
            try:
                await message.answer(reaction)
            except TelegramBadRequest:
                pass

async def chat_id_command(message: Message):
    await message.reply(f"ID этого чата: <code>{message.chat.id}</code>", parse_mode="HTML")

async def on_bot_added(chat_member: ChatMemberUpdated):
    status = chat_member.new_chat_member.status
    if status in ("member", "administrator"):
        try:
            await bot.send_message(chat_member.chat.id, "Я на месте! Фильтрую Ваш базар и веду статистику нарушений 👀")
        except TelegramBadRequest:
            pass

# -------------------- Запуск бота --------------------
async def scheduler():
    while True:
        now = datetime.utcnow()
        # 14:00 по Алматы = 9:00 UTC, 19:00 = 14:00 UTC
        send_times = [9, 14]
        for hour in send_times:
            if now.hour == hour and now.minute == 0:
                await send_stats()
        await asyncio.sleep(60)

async def main():
    global bot, dp
    session = AiohttpSession()
    bot = Bot(token=API_TOKEN, session=session, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.message.register(handle_message)
    dp.message.register(chat_id_command, Command(commands=["chatid"]))
    dp.chat_member.register(on_bot_added)

    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
