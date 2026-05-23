from datetime import datetime, timezone

from telebot import TeleBot, types

import db
from utils.logger import logger
from .natural_parser import parse_event_text
from .keyboards import make_delete_keyboard, confirm_delete_keyboard




def _fmt_dt(iso: str) -> str:
    """Форматирует ISO datetime в читаемый вид."""
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime('%d.%m.%Y %H:%M')
    except Exception:
        return iso


def register_event_handlers(bot: TeleBot):

    # ── /events ───────────────────────────────────────────────────────────────

    @bot.message_handler(commands=['events'])
    def show_events(message):
        user_id = message.from_user.id
        db.ensure_user(user_id)
        events = db.get_upcoming_events(user_id)

        if not events:
            bot.send_message(message.chat.id, "📭 Ближайших событий нет.\n\nДобавьте первое, например:\n<i>Завтра в 15:00 Встреча</i>", parse_mode='HTML')
            return

        bot.send_message(message.chat.id, f"📋 Ближайшие события ({len(events)}):")
        for event in events:
            text = f"📅 <b>{event['summary']}</b>\n🕒 {_fmt_dt(event['event_dt'])}"
            bot.send_message(
                message.chat.id, text,
                parse_mode='HTML',
                reply_markup=make_delete_keyboard(event['id']),
            )

    # ── /add ──────────────────────────────────────────────────────────────────

    @bot.message_handler(commands=['add'])
    def add_command(message):
        user_id = message.from_user.id
        db.ensure_user(user_id)
        text = message.text.replace('/add', '', 1).strip()
        if not text:
            bot.reply_to(
                message,
                "Укажите дату и описание, например:\n"
                "<i>/add Завтра в 15:00 Встреча</i>",
                parse_mode='HTML',
            )
            return
        _process_input(bot, message, text)

    # ── Свободный текст ───────────────────────────────────────────────────────

    @bot.message_handler(func=lambda m: not m.text.startswith('/'))
    def natural_message(message):
        db.ensure_user(message.from_user.id)
        _process_input(bot, message, message.text)

    # ── Callback: удаление ────────────────────────────────────────────────────

    @bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
    def confirm_delete(call: types.CallbackQuery):
        event_id = int(call.data[4:])
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=confirm_delete_keyboard(event_id),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_del_'))
    def do_delete(call: types.CallbackQuery):
        event_id = int(call.data[12:])
        user_id = call.from_user.id
        deleted = db.delete_event(event_id, user_id)
        if deleted:
            bot.edit_message_text(
                "🗑 Событие удалено.",
                call.message.chat.id,
                call.message.message_id,
            )
            logger.info(f"User {user_id} deleted event {event_id}")
        else:
            bot.answer_callback_query(call.id, "Событие не найдено.")

    @bot.callback_query_handler(func=lambda call: call.data == 'cancel_del')
    def cancel_delete(call: types.CallbackQuery):
        bot.answer_callback_query(call.id, "Удаление отменено.")
        bot.edit_message_reply_markup(
            call.message.chat.id,
            call.message.message_id,
            reply_markup=None,
        )


def _process_input(bot: TeleBot, message, text: str):
    user_id = message.from_user.id
    tz = db.get_timezone(user_id)
    dt, summary = parse_event_text(text, tz)

    if dt and summary:
        # Проверяем что дата в будущем
        now = datetime.now(tz=dt.tzinfo or timezone.utc)
        if dt <= now:
            bot.reply_to(message, "⚠️ Дата уже прошла. Укажите будущее время.")
            return
        try:
            event_id = db.add_event(user_id, summary, dt)
            bot.reply_to(
                message,
                f"✅ Событие сохранено!\n\n"
                f"📅 <b>{summary}</b>\n"
                f"🕒 {dt.strftime('%d.%m.%Y %H:%M')}",
                parse_mode='HTML',
            )
            logger.info(f"User {user_id} added event #{event_id}: '{summary}' at {dt}")
        except Exception as e:
            logger.error(f"Add event error for {user_id}: {e}")
            bot.reply_to(message, f"❌ Ошибка при сохранении: {e}")
    else:
        bot.reply_to(
            message,
            "🤔 Не удалось распознать дату/время.\n\n"
            "Попробуйте, например:\n"
            "<i>Завтра в 15:00 Встреча</i>\n"
            "<i>В пятницу в 10:30 Звонок</i>\n"
            "<i>Через 2 часа Купить продукты</i>",
            parse_mode='HTML',
        )
    