import json
import logging
import random
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.client.bot import DefaultBotProperties

API_TOKEN = "6909049704:AAGeTidLhxR7uQoHNlsz4IU9SoD8OW9PMpo"  # <-- вставь свой токен

# --------------------
# Файлы и данные
# --------------------
FORBIDDEN_FILE = Path("forbidden_words.txt")
WARNINGS_FILE = Path("warnings.json")
STATS_FILE = Path("stats.json")
MAX_REACT_LEVEL = 50
IGNORED_USERS = [5470301151]  # Игнорируемые пользователи

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

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

# --------------------
# Сохранение данных
# --------------------
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

# --------------------
# Статистика
# --------------------
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
        lines = [f"👤 {user} → {count}" for user, count in sorted_users[:10]]
        return "\n".join(lines)

    return (
        "🏆 <b>Статистика нарушений</b>\n\n"
        "📅 <b>За последние 24 часа</b>:\n"
        f"{format_top(daily)}\n\n"
        "📈 <b>За последние 7 дней</b>:\n"
        f"{format_top(weekly)}"
    )

def get_next_send_time(now):
    send_hours = [14, 19]
    candidates = []
    for hour in send_hours:
        target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        candidates.append(target)
    return min(candidates)

async def scheduler(bot: Bot, chat_id: int):
    """Авто-отправка статистики каждый день в 14:00 и 19:00 по Алматы (предполагая, что системное время - локальное)"""
    while True:
        now = datetime.now()
        target = get_next_send_time(now)
        await asyncio.sleep((target - now).total_seconds())
        report = generate_stats_report(chat_id)
        try:
            await bot.send_message(chat_id, report)
        except Exception as e:
            log.error(f"Ошибка при отправке статистики: {e}")

# --------------------
# Обработка сообщений
# --------------------
async def handle_message(message: Message, bot: Bot):
    if not message.text or message.from_user.id in IGNORED_USERS:
        return
    if contains_bad_word(message.text):
        try:
            await message.delete()
        except Exception:
            pass
        username = message.from_user.username or message.from_user.first_name
        count = add_warning(message.chat.id, message.from_user.id, username)
        mention = f'<a href="tg://user?id={message.from_user.id}">{message.from_user.first_name}</a>'
        if count % 5 == 0 and count <= MAX_REACT_LEVEL:
            reaction = random.choice(FUNNY_REACTS).format(mention=mention)
            reaction += f"\n\nВсего предупреждений: {count}"
            await message.answer(reaction)

# --------------------
# Команда chatid
# --------------------
async def chatid_command(message: Message):
    await message.reply(f"ID этого чата: <code>{message.chat.id}</code>")

# --------------------
# Команда stats (опционально, для ручного вызова)
# --------------------
async def stats_command(message: Message):
    report = generate_stats_report(message.chat.id)
    await message.reply(report)

# --------------------
# Запуск бота
# --------------------
async def main():
    bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    # Обработчики
    dp.message.register(handle_message, F.text & ~Command())
    dp.message.register(chatid_command, Command(commands=["chatid"]))
    dp.message.register(stats_command, Command(commands=["stats"]))
    # ID чата для автоотправки статистики
    chat_id_for_stats = -1003388389759  # <-- вставь свой канал/чат
    # Старт авто-отправки статистики после запуска
    async def start_scheduler(_):
        asyncio.create_task(scheduler(bot, chat_id_for_stats))
    dp.startup.register(start_scheduler)
    dp.startup.register(lambda _: log.info("Бот запущен"))
    # Запуск polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
