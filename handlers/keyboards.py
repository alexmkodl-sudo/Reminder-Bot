from telebot import types


def make_event_keyboard(event_id: int) -> types.InlineKeyboardMarkup:
    """Кнопки под событием в списке /events."""
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✏️ Изменить", callback_data=f"edit_{event_id}"),
        types.InlineKeyboardButton("🗑 Удалить",  callback_data=f"del_{event_id}"),
    )
    markup.row(
        types.InlineKeyboardButton("✅ Выполнено", callback_data=f"done_{event_id}"),
    )
    return markup


# Обратная совместимость — использовалось в голосовых и т.д.
def make_delete_keyboard(event_id: int) -> types.InlineKeyboardMarkup:
    return make_event_keyboard(event_id)


def confirm_delete_keyboard(event_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_del_{event_id}"),
        types.InlineKeyboardButton("❌ Отмена",      callback_data="cancel_del"),
    )
    return markup


def voice_confirm_keyboard(summary: str, iso_dt: str) -> types.InlineKeyboardMarkup:
    """Подтверждение события из голосового сообщения."""
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton(
            "✅ Сохранить", callback_data=f"vconfirm|{iso_dt}|{summary[:60]}"
        ),
        types.InlineKeyboardButton("❌ Отмена", callback_data="vcancel"),
    )
    return markup


def timezone_keyboard() -> types.InlineKeyboardMarkup:
    """Быстрый выбор популярных часовых поясов."""
    zones = [
        ("🇷🇺 Москва",       "Europe/Moscow"),
        ("🇷🇺 Екатеринбург", "Asia/Yekaterinburg"),
        ("🇷🇺 Новосибирск",  "Asia/Novosibirsk"),
        ("🇷🇺 Владивосток",  "Asia/Vladivostok"),
        ("🇺🇦 Киев",         "Europe/Kyiv"),
        ("🇰🇿 Алматы",       "Asia/Almaty"),
        ("🇬🇧 Лондон",       "Europe/London"),
        ("🇩🇪 Берлин",       "Europe/Berlin"),
        ("🇺🇸 Нью-Йорк",     "America/New_York"),
        ("🇺🇸 Лос-Анджелес", "America/Los_Angeles"),
    ]
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(label, callback_data=f"tz|{tz}")
        for label, tz in zones
    ]
    markup.add(*buttons)
    return markup


def recurrence_keyboard() -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("🔁 Ежедневно",   callback_data="recur|daily"),
        types.InlineKeyboardButton("📅 Еженедельно", callback_data="recur|weekly"),
    )
    markup.row(
        types.InlineKeyboardButton("🗓 Ежемесячно",  callback_data="recur|monthly"),
        types.InlineKeyboardButton("➖ Без повтора",  callback_data="recur|none"),
    )
    return markup
