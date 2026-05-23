import time
import threading
from datetime import datetime, timezone

import telebot

import db
from config import REMINDER_MINUTES
from utils.logger import logger


def _check_and_send(bot: telebot.TeleBot):
    """Проверяет все ближайшие события и отправляет напоминания если нужно."""
    now = datetime.now(tz=timezone.utc)
    events = db.get_all_upcoming_events()

    for event in events:
        event_dt = datetime.fromisoformat(event['event_dt'])
        if event_dt.tzinfo is None:
            event_dt = event_dt.replace(tzinfo=timezone.utc)

        diff_minutes = (event_dt - now).total_seconds() / 60

        for remind_min in REMINDER_MINUTES:
            if remind_min - 1 <= diff_minutes <= remind_min + 1:
                if not db.reminder_already_sent(event['id'], remind_min):
                    try:
                        bot.send_message(
                            event['user_id'],
                            f"🔔 Напоминание! Через <b>{remind_min} мин.</b>:\n"
                            f"📅 <b>{event['summary']}</b>",
                            parse_mode='HTML',
                        )
                        db.mark_reminder_sent(event['id'], remind_min)
                        logger.info(
                            f"Reminder sent: user={event['user_id']} "
                            f"event_id={event['id']} remind={remind_min}min"
                        )
                    except Exception as e:
                        logger.error(f"Failed to send reminder: {e}")


def start_reminder_loop(bot: telebot.TeleBot, interval_seconds: int = 60):
    """Запускает фоновый поток, который каждую минуту проверяет события."""
    def loop():
        logger.info(f"Reminder loop started (interval={interval_seconds}s, "
                    f"remind at: {REMINDER_MINUTES} min before)")
        while True:
            try:
                _check_and_send(bot)
            except Exception as e:
                logger.error(f"Reminder loop error: {e}")
            time.sleep(interval_seconds)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
