from telebot import TeleBot

import db
from config import REMINDER_MINUTES

HELP_TEXT = (
    "📅 <b>Органайзер-бот v3</b>\n\n"
    "Просто напишите или надиктуйте дату и событие — бот сохранит и напомнит!\n\n"
    "<b>Команды:</b>\n"
    "  /events — ближайшие события\n"
    "  /add &lt;текст&gt; — добавить событие (с выбором повтора)\n"
    "  /search &lt;запрос&gt; — поиск по названию\n"
    "  /stats — ваша статистика\n"
    "  /export — скачать .ics для Google/Apple Calendar\n"
    "  /timezone — сменить часовой пояс\n"
    "  /help — эта справка\n\n"
    "<b>Примеры текста:</b>\n"
    "  <i>Завтра в 15:00 Встреча с командой</i>\n"
    "  <i>В пятницу в 10:30 Звонок с клиентом</i>\n"
    "  <i>/add Через 2 часа Купить продукты</i>\n"
    "  🎙 <i>Голосовое: «Завтра в девять утра врач»</i>\n\n"
    "<b>В списке событий доступны кнопки:</b>\n"
    "  ✏️ Изменить · 🗑 Удалить · ✅ Выполнено\n\n"
    f"🔔 Напоминания за: {', '.join(str(m) for m in REMINDER_MINUTES)} мин. "
    "(с кнопками «Выполнено» и «+30 мин»)"
)


def register_start_handlers(bot: TeleBot):

    @bot.message_handler(commands=["start"])
    def start_command(message):
        db.ensure_user(message.from_user.id)
        name = message.from_user.first_name or "друг"
        bot.send_message(
            message.chat.id,
            f"Привет, {name}! 👋\n\n" + HELP_TEXT,
            parse_mode="HTML",
        )

    @bot.message_handler(commands=["help"])
    def help_command(message):
        db.ensure_user(message.from_user.id)
        bot.send_message(message.chat.id, HELP_TEXT, parse_mode="HTML")
