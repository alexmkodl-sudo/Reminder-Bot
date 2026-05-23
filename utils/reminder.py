"""
utils/reminder.py — фоновый планировщик напоминаний.

Улучшения v3:
  - Ловит ApiTelegramException: если пользователь заблокировал бота — деактивируем его в БД.
  - Напоминание приходит с кнопками «✅ Выполнено» и «⏰ Перенести на 30 мин».
  - Повторяющиеся события: после наступления времени создаётся следующее вхождение.
"""

import time
import threading
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta

import telebot
from telebot.apihelper import ApiTelegramException

import db
from config import REMINDER_MINUTES
from utils.logger import logger


def _reminder_keyboard(event_id: int):
    from telebot import types
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ Выполнено",       callback_data=f"done_{event_id}"),
        types.InlineKeyboardButton("⏰ +30 мин",         callback_data=f"snooze_{event_id}"),
    )
    return markup


def _spawn_next_recurrence(event: dict):
    """Создаёт следующее вхождение повторяющегося события."""
    recurrence = event.get("recurrence")
    if not recurrence:
        return
    event_dt = datetime.fromisoformat(event["event_dt"])
    if event_dt.tzinfo is None:
        event_dt = event_dt.replace(tzinfo=timezone.utc)

    if recurrence == "daily":
        next_dt = event_dt + timedelta(days=1)
    elif recurrence == "weekly":
        next_dt = event_dt + timedelta(weeks=1)
    elif recurrence == "monthly":
        next_dt = event_dt + relativedelta(months=1)
    else:
        return

    recur_until = event.get("recur_until")
    if recur_until and next_dt.date().isoformat() > recur_until:
        return

    db.add_event(
        user_id=event["user_id"],
        summary=event["summary"],
        event_dt=next_dt,
        recurrence=recurrence,
        recur_until=datetime.fromisoformat(recur_until) if recur_until else None,
    )
    logger.info(f"Spawned next recurrence for event {event['id']} → {next_dt}")


def _check_and_send(bot: telebot.TeleBot):
    now = datetime.now(tz=timezone.utc)
    events = db.get_all_upcoming_events()

    for event in events:
        event_dt = datetime.fromisoformat(event["event_dt"])
        if event_dt.tzinfo is None:
            event_dt = event_dt.replace(tzinfo=timezone.utc)

        diff_minutes = (event_dt - now).total_seconds() / 60

        for remind_min in REMINDER_MINUTES:
            if remind_min - 1 <= diff_minutes <= remind_min + 1:
                if not db.reminder_already_sent(event["id"], remind_min):
                    try:
                        bot.send_message(
                            event["user_id"],
                            f"🔔 Напоминание! Через <b>{remind_min} мин.</b>:\n"
                            f"📅 <b>{event['summary']}</b>",
                            parse_mode="HTML",
                            reply_markup=_reminder_keyboard(event["id"]),
                        )
                        db.mark_reminder_sent(event["id"], remind_min)
                        logger.info(
                            f"Reminder sent: user={event['user_id']} "
                            f"event_id={event['id']} remind={remind_min}min"
                        )
                    except ApiTelegramException as e:
                        # Пользователь заблокировал бота
                        if e.error_code in (403, 400):
                            logger.warning(
                                f"User {event['user_id']} blocked bot, deactivating."
                            )
                            db.deactivate_user(event["user_id"])
                        else:
                            logger.error(f"Telegram error sending reminder: {e}")
                    except Exception as e:
                        logger.error(f"Failed to send reminder: {e}")

        # Если событие вот-вот наступит (в пределах интервала проверки) — создаём следующее
        if -1 <= diff_minutes <= 1 and event.get("recurrence"):
            _spawn_next_recurrence(event)


def start_reminder_loop(bot: telebot.TeleBot, interval_seconds: int = 60):
    def loop():
        logger.info(
            f"Reminder loop started (interval={interval_seconds}s, "
            f"remind at: {REMINDER_MINUTES} min before)"
        )
        while True:
            try:
                _check_and_send(bot)
            except Exception as e:
                logger.error(f"Reminder loop error: {e}")
            time.sleep(interval_seconds)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()


def register_reminder_callbacks(bot: telebot.TeleBot):
    """Регистрирует callback-кнопки напоминания. Вызывать из main."""

    @bot.callback_query_handler(func=lambda call: call.data.startswith("done_"))
    def on_done(call):
        event_id = int(call.data[5:])
        user_id = call.from_user.id
        if db.mark_event_done(event_id, user_id):
            bot.edit_message_text(
                "✅ Отлично, событие отмечено выполненным!",
                call.message.chat.id,
                call.message.message_id,
            )
        else:
            bot.answer_callback_query(call.id, "Событие не найдено.")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("snooze_"))
    def on_snooze(call):
        event_id = int(call.data[7:])
        user_id = call.from_user.id
        event = db.get_event(event_id, user_id)
        if not event:
            bot.answer_callback_query(call.id, "Событие не найдено.")
            return
        old_dt = datetime.fromisoformat(event["event_dt"])
        if old_dt.tzinfo is None:
            old_dt = old_dt.replace(tzinfo=timezone.utc)
        new_dt = old_dt + timedelta(minutes=30)
        db.update_event(event_id, user_id, event["summary"], new_dt)
        # Сбросим уже отправленные напоминания для этого события
        # (чтобы через 30 мин снова пришло)
        from db.models import get_connection
        conn = get_connection()
        conn.execute("DELETE FROM reminders_sent WHERE event_id=?", (event_id,))
        conn.commit()

        bot.edit_message_text(
            f"⏰ Перенесено на 30 мин.\n📅 <b>{event['summary']}</b>\n"
            f"🕒 {new_dt.strftime('%d.%m.%Y %H:%M')} UTC",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
        )
