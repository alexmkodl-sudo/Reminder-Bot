import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8121483718:AAH3FHfwZ5tr-DfXam4hlYhVEMn95UkvHtw")

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/events.db")

REMINDER_MINUTES = [
    int(x.strip())
    for x in os.getenv("REMINDER_MINUTES", "10,30").split(",")
]

if not BOT_TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не установлена!")
