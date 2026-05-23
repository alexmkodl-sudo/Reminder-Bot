from telebot import TeleBot

import db
from config import REMINDER_MINUTES

HELP_TEXT = (
    "📅 <b>Органайзер-бот</b>\n\n"
    "Просто напишите дату и событие — бот сохранит и напомнит!\n\n"
    "<b>Команды:</b>\n"
    "  /events — ближайшие события\n"
    "  /add &lt;текст&gt; — добавить событие\n"
    "  /help — эта справка\n\n"
    "<b>Примеры:</b>\n"
    "  <i>Завтра в 15:00 Встреча с командой</i>\n"
    "  <i>В пятницу в 10:30 Звонок с клиентом</i>\n"
    "  /add Через 2 часа Купить продукты\n\n"
    f"🔔 Напоминания приходят за: {', '.join(str(m) for m in REMINDER_MINUTES)} мин."
)


def register_start_handlers(bot: TeleBot):

    @bot.message_handler(commands=['start'])
    def start_command(message):
        user_id = message.from_user.id
        db.ensure_user(user_id)
        name = message.from_user.first_name or "друг"
        bot.send_message(
            message.chat.id,
            f"Привет, {name}! 👋\n\n" + HELP_TEXT,
            parse_mode='HTML',
        )

    @bot.message_handler(commands=['help'])
    def help_command(message):
        db.ensure_user(message.from_user.id)
        bot.send_message(message.chat.id, HELP_TEXT, parse_mode='HTML')
