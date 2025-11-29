import json
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram import F

API_TOKEN = "6909049704:AAGeTidLhxR7uQoHNlsz4IU9SoD8OW9PMpo"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Пути к файлам
FORBIDDEN_FILE = Path("forbidden_words.txt")
WARNINGS_FILE = Path("warnings.json")
STATS_FILE = Path("stats.json")

MAX_REACT_LEVEL = 50
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

def log_warning(chat_id, user_id):
    stats_db["history"].append({
        "chat_id": chat_id,
        "user_id": user_id,
        "timestamp": datetime.utcnow().isoformat()
    })
    save_stats()

def contains_bad_word(text: str):
    text = text.lower()
    return any(bad in text for bad in BAD_WORDS)

def add_warning(chat_id, user_id):
    key = f"{chat_id}:{user_id}"
    count = warnings_db.get(key, 0) + 1
    warnings_db[key] = count
    save_warnings()
    log_warning(chat_id, user_id)
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
            lines.append(f"👤 <code>{uid}</code> → {count}")
        return "\n".join(lines)

    return (
        "🏆 <b>Статистика нарушений</b>\n\n"
        "📅 <b>За последние 24 часа</b>:\n"
        f"{format_top(daily)}\n\n"
        "📈 <b>За последние 7 дней</b>:\n"
        f"{format_top(weekly)}"
    )

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ---------------------------
# Обработка сообщений
# ---------------------------
@dp.message(F.text)
async def handle_message(message: types.Message):
    user = message.from_user
    chat_id = message.chat.id

    if user.id in IGNORED_USERS:
        return

    text = message.text
    if contains_bad_word(text):
        # Удаляем сообщение
        try:
            await message.delete()
        except:
            pass

        count = add_warning(chat_id, user.id)
        mention = message.from_user.get_mention(as_html=True)

        if count % 5 == 0 and count <= MAX_REACT_LEVEL:
            reaction = random.choice(FUNNY_REACTS).format(mention=mention)
            reaction += f"\n\nВсего предупреждений: {count}"
            await message.answer(reaction, parse_mode=ParseMode.HTML)

# ---------------------------
# Команда для chat_id
# ---------------------------
@dp.message(Command(commands=["chatid"]))
async def chat_id_command(message: types.Message):
    await message.reply(f"ID этого чата: <code>{message.chat.id}</code>", parse_mode=ParseMode.HTML)

# ---------------------------
# Команда для статистики
# ---------------------------
@dp.message(Command(commands=["stats"]))
async def stats_command(message: types.Message):
    report = generate_stats_report(message.chat.id)
    await message.reply(report, parse_mode=ParseMode.HTML)

# ---------------------------
# Запуск бота
# ---------------------------
if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))
