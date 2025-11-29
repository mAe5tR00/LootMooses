import json
import logging
import random
from datetime import time, datetime, timedelta
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode, ChatMemberStatus
from telegram.ext import (
    ApplicationBuilder, MessageHandler, filters,
    ContextTypes, ChatMemberHandler, CommandHandler
)

API_TOKEN = "6909049704:AAGeTidLhxR7uQoHNlsz4IU9SoD8OW9PMpo"

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
# 📊 ГЕНЕРАЦИЯ СТАТИСТИКИ
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

async def send_stats(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    report = generate_stats_report(chat_id)
    await context.bot.send_message(
        chat_id,
        report,
        parse_mode=ParseMode.HTML
    )

# ---------------------------
# 📌 ОБРАБОТКА СООБЩЕНИЙ
# ---------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.message.from_user
    chat_id = update.message.chat.id

    # Игнорируем определённых пользователей
    if user.id in IGNORED_USERS:
        return

    text = update.message.text
    if contains_bad_word(text):
        # Удаляем сообщение
        try:
            await update.message.delete()
        except:
            pass

        count = add_warning(chat_id, user.id)
        mention = user.mention_html()

        if count % 5 == 0 and count <= MAX_REACT_LEVEL:
            reaction = random.choice(FUNNY_REACTS).format(mention=mention)
            reaction += f"\n\nВсего предупреждений: {count}"
            await context.bot.send_message(
                chat_id,
                reaction,
                parse_mode=ParseMode.HTML
            )

# ---------------------------
# 📌 Команда для определения chat_id
# ---------------------------
async def chat_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat.id
    # Ответ бота прямо на твоё сообщение
    await update.message.reply_text(f"ID этого чата: <code>{chat_id}</code>", parse_mode=ParseMode.HTML)

async def on_bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_status = update.my_chat_member.new_chat_member.status
    chat_id = update.my_chat_member.chat.id
    if new_status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER):
        await context.bot.send_message(
            chat_id,
            "Я на месте! Фильтрую Ваш базар и веду статистику нарушений 👀"
        )

def main():
    # Создаём приложение (JobQueue автоматически создаётся, если установлен PTB с job-queue)
    app = ApplicationBuilder().token(API_TOKEN).build()

    # Обработчики
    app.add_handler(ChatMemberHandler(on_bot_added, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CommandHandler("chatid", chat_id_command))  # <-- команда для получения chat_id

    # ID чата для статистики
    chat_id = -1003388389759  # <-- Заменить на ID своего чата!

    # ⏰ Планировщик
    app.job_queue.run_daily(send_stats, time=time(9, 0), data={"chat_id": chat_id})   # 14:00 по Алматы
    app.job_queue.run_daily(send_stats, time=time(14, 0), data={"chat_id": chat_id})  # 19:00 по Алматы

    app.run_polling()

if __name__ == "__main__":
    main()
