"""
handlers/events.py — все обработчики, связанные с событиями.

Новое в v3:
  ✅ /search <запрос>      — поиск по названию
  ✅ /stats                — статистика пользователя
  ✅ /export               — скачать .ics файл
  ✅ /timezone             — сменить часовой пояс
  ✅ /add с флагом повтора — кнопки выбора recurrence
  ✅ Редактирование        — callback edit_ → пошаговый FSM
  ✅ Подтверждение         — только для голосовых сообщений
  ✅ Кнопки done_/snooze_  — уже в reminder.py, здесь done_ дублируем для /events
"""

import io
import pytz
from datetime import datetime, timezone, timedelta

from telebot import TeleBot, types
from telebot.handler_backends import State, StatesGroup
from telebot.storage import StateMemoryStorage

import db
from utils.logger import logger
from .natural_parser import parse_event_text
from .keyboards import (
    make_event_keyboard,
    confirm_delete_keyboard,
    voice_confirm_keyboard,
    timezone_keyboard,
    recurrence_keyboard,
)


# ── FSM состояния ─────────────────────────────────────────────────────────────

class EditStates(StatesGroup):
    waiting_new_text = State()


# ── Вспомогательные функции ───────────────────────────────────────────────────

def _fmt_dt(iso: str, user_tz: str = "UTC") -> str:
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        tz = pytz.timezone(user_tz)
        dt_local = dt.astimezone(tz)
        return dt_local.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return iso


def _event_text(event: dict, user_tz: str = "UTC") -> str:
    recur_label = {
        "daily": " 🔁 ежедневно",
        "weekly": " 📅 еженедельно",
        "monthly": " 🗓 ежемесячно",
    }.get(event.get("recurrence") or "", "")
    return (
        f"📅 <b>{event['summary']}</b>{recur_label}\n"
        f"🕒 {_fmt_dt(event['event_dt'], user_tz)}"
    )


def _make_ics(events: list[dict], user_tz: str) -> bytes:
    """Генерирует .ics файл из списка событий."""
    tz = pytz.timezone(user_tz)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//OrganizerBot//RU",
        "CALSCALE:GREGORIAN",
    ]
    for ev in events:
        dt = datetime.fromisoformat(ev["event_dt"])
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_local = dt.astimezone(tz)
        stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dtstart = dt_local.strftime("%Y%m%dT%H%M%S")
        tzid = user_tz
        summary = ev["summary"].replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev['id']}@organizerbot",
            f"DTSTAMP:{stamp}",
            f"DTSTART;TZID={tzid}:{dtstart}",
            f"SUMMARY:{summary}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines).encode("utf-8")


# ── Регистрация обработчиков ──────────────────────────────────────────────────

def register_event_handlers(bot: TeleBot):

    # ── /events ───────────────────────────────────────────────────────────────

    @bot.message_handler(commands=["events"])
    def show_events(message):
        user_id = message.from_user.id
        db.ensure_user(user_id)
        user_tz = db.get_timezone(user_id)
        events = db.get_upcoming_events(user_id)
        if not events:
            bot.send_message(
                message.chat.id,
                "📭 Ближайших событий нет.\n\nДобавьте первое, например:\n"
                "<i>Завтра в 15:00 Встреча</i>",
                parse_mode="HTML",
            )
            return
        bot.send_message(message.chat.id, f"📋 Ближайшие события ({len(events)}):")
        for event in events:
            bot.send_message(
                message.chat.id,
                _event_text(event, user_tz),
                parse_mode="HTML",
                reply_markup=make_event_keyboard(event["id"]),
            )

    # ── /add ──────────────────────────────────────────────────────────────────

    @bot.message_handler(commands=["add"])
    def add_command(message):
        user_id = message.from_user.id
        db.ensure_user(user_id)
        text = message.text.replace("/add", "", 1).strip()
        if not text:
            bot.reply_to(
                message,
                "Укажите дату и описание, например:\n<i>/add Завтра в 15:00 Встреча</i>",
                parse_mode="HTML",
            )
            return
        _process_input(bot, message, text, ask_recurrence=True)

    # ── /search ───────────────────────────────────────────────────────────────

    @bot.message_handler(commands=["search"])
    def search_command(message):
        user_id = message.from_user.id
        db.ensure_user(user_id)
        query = message.text.replace("/search", "", 1).strip()
        if not query:
            bot.reply_to(message, "Укажите поисковый запрос: <i>/search встреча</i>", parse_mode="HTML")
            return
        user_tz = db.get_timezone(user_id)
        results = db.search_events(user_id, query)
        if not results:
            bot.reply_to(message, f"🔍 По запросу «{query}» ничего не найдено.")
            return
        bot.send_message(message.chat.id, f"🔍 Найдено ({len(results)}):")
        for event in results:
            bot.send_message(
                message.chat.id,
                _event_text(event, user_tz),
                parse_mode="HTML",
                reply_markup=make_event_keyboard(event["id"]),
            )

    # ── /stats ────────────────────────────────────────────────────────────────

    @bot.message_handler(commands=["stats"])
    def stats_command(message):
        user_id = message.from_user.id
        db.ensure_user(user_id)
        s = db.get_stats(user_id)
        text = (
            "📊 <b>Ваша статистика</b>\n\n"
            f"📝 Всего создано событий: <b>{s['total']}</b>\n"
            f"✅ Выполнено: <b>{s['done']}</b>\n"
            f"⏳ Предстоит: <b>{s['upcoming']}</b>"
        )
        bot.send_message(message.chat.id, text, parse_mode="HTML")

    # ── /export ───────────────────────────────────────────────────────────────

    @bot.message_handler(commands=["export"])
    def export_command(message):
        user_id = message.from_user.id
        db.ensure_user(user_id)
        user_tz = db.get_timezone(user_id)
        events = db.get_upcoming_events(user_id, limit=200)
        if not events:
            bot.reply_to(message, "📭 Нет предстоящих событий для экспорта.")
            return
        ics_bytes = _make_ics(events, user_tz)
        bot.send_document(
            message.chat.id,
            ("events.ics", io.BytesIO(ics_bytes), "text/calendar"),
            caption=f"📅 Экспорт {len(events)} событий. Откройте в Google Calendar, Apple Calendar или Outlook.",
        )

    # ── /timezone ─────────────────────────────────────────────────────────────

    @bot.message_handler(commands=["timezone"])
    def timezone_command(message):
        db.ensure_user(message.from_user.id)
        current = db.get_timezone(message.from_user.id)
        bot.send_message(
            message.chat.id,
            f"🌍 Текущий часовой пояс: <b>{current}</b>\n\nВыберите новый:",
            parse_mode="HTML",
            reply_markup=timezone_keyboard(),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("tz|"))
    def on_timezone_select(call: types.CallbackQuery):
        tz_name = call.data[3:]
        try:
            pytz.timezone(tz_name)  # валидация
        except pytz.UnknownTimeZoneError:
            bot.answer_callback_query(call.id, "Неизвестный часовой пояс.")
            return
        db.set_timezone(call.from_user.id, tz_name)
        bot.edit_message_text(
            f"✅ Часовой пояс установлен: <b>{tz_name}</b>",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
        )

    # ── Голосовые сообщения ───────────────────────────────────────────────────

    @bot.message_handler(content_types=["voice"])
    def voice_message(message):
        user_id = message.from_user.id
        db.ensure_user(user_id)

        from config import OPENAI_API_KEY
        if not OPENAI_API_KEY:
            bot.reply_to(message, "⚠️ Голосовые недоступны: не задан OPENAI_API_KEY.")
            return

        wait_msg = bot.reply_to(message, "🎙 Распознаю голосовое сообщение...")
        try:
            from .voice import transcribe_voice
            file_info = bot.get_file(message.voice.file_id)
            file_bytes = bot.download_file(file_info.file_path)
            text = transcribe_voice(file_bytes, OPENAI_API_KEY)

            if not text:
                bot.edit_message_text(
                    "❌ Не удалось распознать речь. Попробуйте говорить чётче.",
                    message.chat.id, wait_msg.message_id,
                )
                return

            user_tz = db.get_timezone(user_id)
            dt, summary = parse_event_text(text, user_tz)

            if not dt or not summary:
                bot.edit_message_text(
                    f"🎙 Распознано:\n<i>{text}</i>\n\n"
                    "🤔 Не удалось распознать дату/время. Попробуйте ещё раз.",
                    message.chat.id, wait_msg.message_id, parse_mode="HTML",
                )
                return

            # ── Подтверждение (только для голосовых) ──────────────────────────
            dt_utc = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            now_utc = datetime.now(tz=timezone.utc)
            if dt_utc <= now_utc:
                bot.edit_message_text(
                    f"🎙 Распознано:\n<i>{text}</i>\n\n⚠️ Дата уже прошла.",
                    message.chat.id, wait_msg.message_id, parse_mode="HTML",
                )
                return

            dt_display = _fmt_dt(dt_utc.isoformat(), user_tz)
            bot.edit_message_text(
                f"🎙 Распознано:\n<i>{text}</i>\n\n"
                f"Создать событие?\n\n"
                f"📅 <b>{summary}</b>\n🕒 {dt_display}",
                message.chat.id, wait_msg.message_id,
                parse_mode="HTML",
                reply_markup=voice_confirm_keyboard(summary, dt_utc.isoformat()),
            )
        except Exception as e:
            logger.error(f"Voice handler error for user {user_id}: {e}")
            bot.edit_message_text(
                "❌ Ошибка при обработке голосового сообщения.",
                message.chat.id, wait_msg.message_id,
            )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("vconfirm|"))
    def on_voice_confirm(call: types.CallbackQuery):
        _, iso_dt, summary = call.data.split("|", 2)
        user_id = call.from_user.id
        dt = datetime.fromisoformat(iso_dt)
        try:
            event_id = db.add_event(user_id, summary, dt)
            user_tz = db.get_timezone(user_id)
            bot.edit_message_text(
                f"✅ Событие сохранено!\n\n"
                f"📅 <b>{summary}</b>\n"
                f"🕒 {_fmt_dt(iso_dt, user_tz)}",
                call.message.chat.id, call.message.message_id,
                parse_mode="HTML",
                reply_markup=make_event_keyboard(event_id),
            )
            logger.info(f"User {user_id} saved voice event #{event_id}: '{summary}' at {dt}")
        except Exception as e:
            logger.error(f"Voice confirm error: {e}")
            bot.answer_callback_query(call.id, "Ошибка при сохранении.")

    @bot.callback_query_handler(func=lambda call: call.data == "vcancel")
    def on_voice_cancel(call: types.CallbackQuery):
        bot.edit_message_text(
            "❌ Создание события отменено.",
            call.message.chat.id, call.message.message_id,
        )

    # ── Recurrence: выбор повтора ──────────────────────────────────────────────

    @bot.callback_query_handler(func=lambda call: call.data.startswith("recur|"))
    def on_recurrence_select(call: types.CallbackQuery):
        """
        Данные в call.message.text уже содержат заготовленное событие.
        Мы кодируем summary и iso_dt в reply_markup через pending_event в bot.user_data.
        """
        recurrence = call.data[6:]  # daily / weekly / monthly / none
        # Достаём pending event из хранилища
        pending = _pending_events.pop(call.from_user.id, None)
        if not pending:
            bot.answer_callback_query(call.id, "Сессия истекла. Введите событие заново.")
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            return

        user_id = call.from_user.id
        summary = pending["summary"]
        dt = pending["dt"]
        rec = None if recurrence == "none" else recurrence
        try:
            event_id = db.add_event(user_id, summary, dt, recurrence=rec)
            user_tz = db.get_timezone(user_id)
            rec_label = {"daily": " 🔁 ежедневно", "weekly": " 📅 еженедельно",
                         "monthly": " 🗓 ежемесячно"}.get(rec or "", "")
            bot.edit_message_text(
                f"✅ Событие сохранено{rec_label}!\n\n"
                f"📅 <b>{summary}</b>\n"
                f"🕒 {_fmt_dt(dt.isoformat(), user_tz)}",
                call.message.chat.id, call.message.message_id,
                parse_mode="HTML",
                reply_markup=make_event_keyboard(event_id),
            )
            logger.info(f"User {user_id} added event #{event_id}: '{summary}' rec={rec}")
        except Exception as e:
            logger.error(f"Recurrence save error: {e}")
            bot.answer_callback_query(call.id, "Ошибка при сохранении.")

    # ── Редактирование события ────────────────────────────────────────────────

    @bot.callback_query_handler(func=lambda call: call.data.startswith("edit_"))
    def on_edit(call: types.CallbackQuery):
        event_id = int(call.data[5:])
        user_id = call.from_user.id
        event = db.get_event(event_id, user_id)
        if not event:
            bot.answer_callback_query(call.id, "Событие не найдено.")
            return
        _edit_sessions[user_id] = event_id
        user_tz = db.get_timezone(user_id)
        bot.send_message(
            call.message.chat.id,
            f"✏️ Редактируем событие:\n"
            f"📅 <b>{event['summary']}</b>\n"
            f"🕒 {_fmt_dt(event['event_dt'], user_tz)}\n\n"
            "Введите новый текст с датой (или /cancel):",
            parse_mode="HTML",
        )
        bot.answer_callback_query(call.id)

    # ── Удаление ──────────────────────────────────────────────────────────────

    @bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
    def on_del(call: types.CallbackQuery):
        event_id = int(call.data[4:])
        bot.edit_message_reply_markup(
            call.message.chat.id, call.message.message_id,
            reply_markup=confirm_delete_keyboard(event_id),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_del_"))
    def do_delete(call: types.CallbackQuery):
        event_id = int(call.data[12:])
        user_id = call.from_user.id
        if db.delete_event(event_id, user_id):
            bot.edit_message_text(
                "🗑 Событие удалено.",
                call.message.chat.id, call.message.message_id,
            )
            logger.info(f"User {user_id} deleted event {event_id}")
        else:
            bot.answer_callback_query(call.id, "Событие не найдено.")

    @bot.callback_query_handler(func=lambda call: call.data == "cancel_del")
    def cancel_delete(call: types.CallbackQuery):
        bot.answer_callback_query(call.id, "Удаление отменено.")
        bot.edit_message_reply_markup(
            call.message.chat.id, call.message.message_id, reply_markup=None,
        )

    # ── Выполнено (из списка /events) ─────────────────────────────────────────

    @bot.callback_query_handler(func=lambda call: call.data.startswith("done_"))
    def on_done(call: types.CallbackQuery):
        event_id = int(call.data[5:])
        user_id = call.from_user.id
        if db.mark_event_done(event_id, user_id):
            bot.edit_message_text(
                "✅ Событие отмечено выполненным!",
                call.message.chat.id, call.message.message_id,
            )
        else:
            bot.answer_callback_query(call.id, "Событие не найдено.")

    # ── Свободный текст ───────────────────────────────────────────────────────

    @bot.message_handler(func=lambda m: m.text is not None and not m.text.startswith("/"))
    def natural_message(message):
        user_id = message.from_user.id
        db.ensure_user(user_id)

        # Режим редактирования?
        if user_id in _edit_sessions:
            _handle_edit_reply(bot, message)
            return

        _process_input(bot, message, message.text, ask_recurrence=False)

    @bot.message_handler(commands=["cancel"])
    def cancel_command(message):
        user_id = message.from_user.id
        if user_id in _edit_sessions:
            del _edit_sessions[user_id]
            bot.reply_to(message, "✖️ Редактирование отменено.")
        else:
            bot.reply_to(message, "Нечего отменять.")


# ── Внутреннее состояние (in-memory FSM) ──────────────────────────────────────

_edit_sessions: dict[int, int] = {}    # user_id → event_id
_pending_events: dict[int, dict] = {}  # user_id → {summary, dt}


def _handle_edit_reply(bot: TeleBot, message):
    user_id = message.from_user.id
    event_id = _edit_sessions.pop(user_id)
    user_tz = db.get_timezone(user_id)
    dt, summary = parse_event_text(message.text, user_tz)

    if not dt or not summary:
        bot.reply_to(
            message,
            "🤔 Не удалось распознать дату/время. Попробуйте ещё раз или /cancel.",
        )
        _edit_sessions[user_id] = event_id  # вернём в режим редактирования
        return

    now_utc = datetime.now(tz=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    if dt_utc <= now_utc:
        bot.reply_to(message, "⚠️ Дата уже прошла. Введите другое время или /cancel.")
        _edit_sessions[user_id] = event_id
        return

    if db.update_event(event_id, user_id, summary, dt):
        bot.reply_to(
            message,
            f"✅ Событие обновлено!\n\n"
            f"📅 <b>{summary}</b>\n"
            f"🕒 {_fmt_dt(dt_utc.isoformat(), user_tz)}",
            parse_mode="HTML",
            reply_markup=make_event_keyboard(event_id),
        )
        logger.info(f"User {user_id} edited event #{event_id}")
    else:
        bot.reply_to(message, "❌ Событие не найдено или уже удалено.")


def _process_input(bot: TeleBot, message, text: str, ask_recurrence: bool = False):
    user_id = message.from_user.id
    user_tz = db.get_timezone(user_id)
    dt, summary = parse_event_text(text, user_tz)

    if dt and summary:
        now_utc = datetime.now(tz=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        if dt_utc <= now_utc:
            bot.reply_to(message, "⚠️ Дата уже прошла. Укажите будущее время.")
            return

        if ask_recurrence:
            # Сохраняем pending и спрашиваем про повтор
            _pending_events[user_id] = {"summary": summary, "dt": dt}
            bot.reply_to(
                message,
                f"📅 <b>{summary}</b>\n🕒 {_fmt_dt(dt_utc.isoformat(), user_tz)}\n\n"
                "🔁 Сделать повторяющимся?",
                parse_mode="HTML",
                reply_markup=recurrence_keyboard(),
            )
        else:
            try:
                event_id = db.add_event(user_id, summary, dt)
                bot.reply_to(
                    message,
                    f"✅ Событие сохранено!\n\n"
                    f"📅 <b>{summary}</b>\n"
                    f"🕒 {_fmt_dt(dt_utc.isoformat(), user_tz)}",
                    parse_mode="HTML",
                    reply_markup=make_event_keyboard(event_id),
                )
                logger.info(f"User {user_id} added event #{event_id}: '{summary}' at {dt}")
            except Exception as e:
                logger.error(f"Add event error for {user_id}: {e}")
                bot.reply_to(message, f"❌ Ошибка при сохранении: {e}")
    else:
        bot.reply_to(
            message,
            "🤔 Не удалось распознать дату/время.\n\n"
            "Попробуйте:\n"
            "<i>Завтра в 15:00 Встреча</i>\n"
            "<i>В пятницу в 10:30 Звонок</i>\n"
            "<i>Через 2 часа Купить продукты</i>",
            parse_mode="HTML",
        )
