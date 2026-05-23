from telebot import types


def make_delete_keyboard(event_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🗑 Удалить", callback_data=f"del_{event_id}"))
    return markup


def confirm_delete_keyboard(event_id: int) -> types.InlineKeyboardMarkup:
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_del_{event_id}"),
        types.InlineKeyboardButton("❌ Отмена",      callback_data="cancel_del"),
    )
    return markup
