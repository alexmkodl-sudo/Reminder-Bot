import os

# Токен Telegram-бота (получить у @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Путь к SQLite базе данных
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/events.db")

# За сколько минут до события присылать напоминание (можно несколько через запятую)
# Пример: "10,30,60" — за 10, 30 и 60 минут
REMINDER_MINUTES = [
    int(x.strip())
    for x in os.getenv("REMINDER_MINUTES", "10,30").split(",")
]

if not BOT_TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не установлена!")
