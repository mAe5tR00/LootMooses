import json
import logging
import random
import asyncio
from datetime import datetime, timedelta

from pathlib import Path
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

API_TOKEN = "6909049704:AAGeTidLhxR7uQoHNlsz4IU9SoD8OW9PMpo"

# --- Настройки файлов ---
FORBIDDEN_FILE = Path("forbidden_words.txt")
WARNINGS_FILE = Path("warnings.json")
STATS_FILE = Path("stats.json")

MAX_REACT_LEVEL = 50
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

# --- Функции работы с файлами ---
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

# ---------------------------
# Генерация статистики
# ---------------------------
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
        return "\n".join(f"👤 <code>{uid}</code> → {count}" for uid, count in sorted_users[:10])

    return (
        "🏆 <b>Статистика нарушений</b>\n\n"
        "📅 <b>За последние 24 часа</b>:\n"
        f"{format_top(daily)}\n\n"
        "📈 <b>За последние 7 дней</b>:\n"
        f"{format_top(weekly)}"
    )

# ---------------------------
# Обработчики сообщений
# ---------------------------
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
        except Exception:
            pass

        count = add_warning(chat_id, user.id)
        mention = user.mention_html()

        if count % 5 == 0 and count <= MAX_REACT_LEVEL:
            reaction = random.choice(FUNNY_REACTS).format(mention=mention)
            reaction += f"\n\nВсего предупреждений: {count}"
            await message.answer(reaction, parse_mode="HTML")

# ---------------------------
# Команда для получения chat_id
# ---------------------------
async def chatid_command(message: types.Message):
    chat_id = message.chat.id
    await message.reply(f"ID этого чата: <code>{chat_id}</code>", parse_mode="HTML")

# ---------------------------
# Фоновая задача для отправки статистики
# ---------------------------
async def stats_loop(bot: Bot, chat_id: int):
    while True:
        report = generate_stats_report(chat_id)
        try:
            await bot.send_message(chat_id, report, parse_mode="HTML")
        except Exception as e:
            log.error(f"Ошибка при отправке статистики: {e}")
        # Ждем до следующего раза (пример: 14:00 и 19:00 по Алматы UTC+5)
        now = datetime.utcnow()
        next_times = [now.replace(hour=9, minute=0, second=0, microsecond=0),
                      now.replace(hour=14, minute=0, second=0, microsecond=0)]
        next_send = min(t for t in next_times if t > now)
        wait_seconds = (next_send - now).total_seconds()
        await asyncio.sleep(wait_seconds)

# ---------------------------
# Запуск бота
# ---------------------------
async def main():
    bot = Bot(token=API_TOKEN)
    dp = Dispatcher()

    # Обработчики
    dp.message.register(handle_message)
    dp.message.register(chatid_command, Command(commands=["chatid"]))

    chat_id = -1003388389759  # <-- Вставь сюда свой chat_id

    # Запуск фона
    asyncio.create_task(stats_loop(bot, chat_id))

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

