"""Handlers for viewing and editing party info (date, address, map, description)."""

from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from bot import database as db
from bot.keyboards import (
    edit_info_field_keyboard,
    edit_info_keyboard,
    main_menu_keyboard,
    party_info_keyboard,
)
from bot.utils import esc

NOT_A_MEMBER_TEXT = "⚠️ You are no longer a member of this party."

FIELD_LABELS = {
    "info_datetime": "🕐 Date & time",
    "info_address": "📍 Address",
    "info_map_link": "🗺 Map link",
    "info_description": "📝 Description",
}

# Conversation state
TYPING_INFO_VALUE = 0


def _build_info_text(party_name: str, info: dict) -> str:
    """Build the formatted party info message."""
    lines = [f"ℹ️ <b>Party info for {esc(party_name)}</b>\n"]

    if info.get("info_datetime"):
        lines.append(f"🕐 <b>Date & time:</b> {esc(info['info_datetime'])}")
    if info.get("info_address"):
        lines.append(f"📍 <b>Address:</b> {esc(info['info_address'])}")
    if info.get("info_map_link"):
        link = info["info_map_link"]
        lines.append(f'🗺 <b>Map:</b> <a href="{esc(link)}">{esc(link)}</a>')
    if info.get("info_description"):
        lines.append(f"📝 <b>Notes:</b> {esc(info['info_description'])}")

    if len(lines) == 1:
        lines.append("No info has been added yet.")

    return "\n".join(lines)


# --------------- View party info ---------------

async def party_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show party info to any member."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])

    user = update.effective_user
    member = await db.get_member(party_id, user.id)
    if member is None:
        await query.edit_message_text(NOT_A_MEMBER_TEXT, reply_markup=main_menu_keyboard())
        return

    party = await db.get_party_by_id(party_id)
    if party is None:
        await query.edit_message_text("Party not found.", reply_markup=main_menu_keyboard())
        return

    info = await db.get_party_info(party_id)
    is_admin = bool(member.get("is_admin"))

    await query.edit_message_text(
        _build_info_text(party["name"], info or {}),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=party_info_keyboard(party_id, is_admin=is_admin),
    )


# --------------- Edit info menu ---------------

async def edit_party_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: show field selection keyboard."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])

    user = update.effective_user
    if not await db.is_user_admin(party_id, user.id):
        await query.edit_message_text("You don't have permission to do this.")
        return

    party = await db.get_party_by_id(party_id)
    if party is None:
        await query.edit_message_text("Party not found.", reply_markup=main_menu_keyboard())
        return

    info = await db.get_party_info(party_id) or {}

    await query.edit_message_text(
        f"✏️ <b>Edit info for {esc(party['name'])}</b>\n\n"
        "Tap a field to set or change it.\n"
        "✅ = already set",
        parse_mode="HTML",
        reply_markup=edit_info_keyboard(party_id, info),
    )


# --------------- Set info field (conversation) ---------------

async def set_info_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin tapped a field to edit — prompt for input."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    party_id = int(parts[1])
    field = parts[2]

    if field not in db.INFO_FIELDS:
        await query.edit_message_text("Invalid field.")
        return ConversationHandler.END

    user = update.effective_user
    if not await db.is_user_admin(party_id, user.id):
        await query.edit_message_text("You don't have permission to do this.")
        return ConversationHandler.END

    info = await db.get_party_info(party_id) or {}
    current = info.get(field)
    label = FIELD_LABELS.get(field, field)

    context.user_data["edit_info_party_id"] = party_id
    context.user_data["edit_info_field"] = field

    text = f"✏️ <b>{label}</b>\n\n"
    if current:
        text += f"Current value: {esc(current)}\n\n"
    text += "Type the new value:"

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=edit_info_field_keyboard(party_id, field, bool(current)),
    )
    return TYPING_INFO_VALUE


async def receive_info_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the typed info value."""
    party_id = context.user_data.get("edit_info_party_id")
    field = context.user_data.get("edit_info_field")
    user = update.effective_user

    if not await db.is_user_admin(party_id, user.id):
        await update.message.reply_text("You don't have permission to do this.")
        return ConversationHandler.END

    value = update.message.text.strip()
    if not value:
        await update.message.reply_text(
            "Value can't be empty. Type something or cancel.",
            reply_markup=edit_info_field_keyboard(party_id, field, False),
        )
        return TYPING_INFO_VALUE

    if len(value) > 500:
        await update.message.reply_text(
            "⚠️ Too long (max 500 characters). Try shorter.",
            reply_markup=edit_info_field_keyboard(party_id, field, False),
        )
        return TYPING_INFO_VALUE

    # Validate map link is a proper URL
    if field == "info_map_link" and not (value.startswith("http://") or value.startswith("https://")):
        await update.message.reply_text(
            "⚠️ Map link must start with http:// or https://",
            reply_markup=edit_info_field_keyboard(party_id, field, False),
        )
        return TYPING_INFO_VALUE

    await db.update_party_info(party_id, field, value)

    label = FIELD_LABELS.get(field, field)
    party = await db.get_party_by_id(party_id)
    if party is None:
        await update.message.reply_text("Party not found.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END
    info = await db.get_party_info(party_id) or {}

    await update.message.reply_text(
        f"✅ {label} updated!\n\n" + _build_info_text(party["name"], info),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=edit_info_keyboard(party_id, info),
    )
    return ConversationHandler.END


async def cancel_set_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel editing and go back to edit info menu."""
    query = update.callback_query
    await query.answer()
    party_id = context.user_data.get("edit_info_party_id")

    if party_id:
        party = await db.get_party_by_id(party_id)
        if party is None:
            await query.edit_message_text("Party not found.", reply_markup=main_menu_keyboard())
            return ConversationHandler.END
        info = await db.get_party_info(party_id) or {}
        await query.edit_message_text(
            f"✏️ <b>Edit info for {esc(party['name'])}</b>\n\n"
            "Tap a field to set or change it.\n"
            "✅ = already set",
            parse_mode="HTML",
            reply_markup=edit_info_keyboard(party_id, info),
        )
    else:
        await query.edit_message_text("Cancelled.")
    return ConversationHandler.END


# --------------- Clear info field ---------------

async def clear_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Admin: clear a single info field.

    Can be called as a plain callback OR as a conversation fallback
    (when user clicks 'Clear' while in set_info conversation).
    Returns ConversationHandler.END when used as fallback.
    """
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    party_id = int(parts[1])
    field = parts[2]

    if field not in db.INFO_FIELDS:
        await query.edit_message_text("Invalid field.")
        return ConversationHandler.END

    user = update.effective_user
    if not await db.is_user_admin(party_id, user.id):
        await query.edit_message_text("You don't have permission to do this.")
        return ConversationHandler.END

    party = await db.get_party_by_id(party_id)
    if party is None:
        await query.edit_message_text("Party not found.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    await db.update_party_info(party_id, field, None)

    info = await db.get_party_info(party_id) or {}
    label = FIELD_LABELS.get(field, field)

    await query.edit_message_text(
        f"🗑 {label} cleared.\n\n"
        f"✏️ <b>Edit info for {esc(party['name'])}</b>\n\n"
        "Tap a field to set or change it.\n"
        "✅ = already set",
        parse_mode="HTML",
        reply_markup=edit_info_keyboard(party_id, info),
    )
    return ConversationHandler.END


# --------------- Conversation builder ---------------

def set_info_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(set_info_start, pattern=r"^set_info:\d+:info_\w+$"),
        ],
        states={
            TYPING_INFO_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_info_value),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(clear_info_callback, pattern=r"^clear_info:\d+:info_\w+$"),
            CallbackQueryHandler(cancel_set_info, pattern=r"^edit_party_info:\d+$"),
        ],
        per_message=False,
    )
