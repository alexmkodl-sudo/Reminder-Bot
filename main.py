import telebot

from config import BOT_TOKEN
from utils.logger import logger
from utils.reminder import start_reminder_loop, register_reminder_callbacks
from db import init_db
from handlers import register_start_handlers, register_event_handlers


def main():
    init_db()
    logger.info("База данных инициализирована")

    bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)

    register_start_handlers(bot)
    register_event_handlers(bot)
    register_reminder_callbacks(bot)   # snooze + done из напоминаний

    start_reminder_loop(bot, interval_seconds=60)

    logger.info("Бот запущен (v3)")
    bot.infinity_polling()


if __name__ == "__main__":
    main()
