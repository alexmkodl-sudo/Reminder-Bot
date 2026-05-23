import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/events.db")

REMINDER_MINUTES = [
    int(x.strip())
    for x in os.getenv("REMINDER_MINUTES", "10,30").split(",")
]

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

if not BOT_TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не установлена!")
