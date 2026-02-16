"""Handlers for viewing and editing party info (date, address, map, description)."""

import json
import logging
import re
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from telegram_bot_calendar import WMonthTelegramCalendar, LSTEP

from bot import database as db
from bot.keyboards import (
    edit_info_field_keyboard,
    edit_info_keyboard,
    main_menu_keyboard,
    party_info_keyboard,
    time_picker_keyboard,
)
from bot.utils import esc

logger = logging.getLogger(__name__)

NOT_A_MEMBER_TEXT = "⚠️ You are no longer a member of this party."

FIELD_LABELS = {
    "info_datetime": "🕐 Date & time",
    "info_address": "📍 Address",
    "info_map_link": "🗺 Map link",
    "info_description": "📝 Description",
}

FIELD_PROMPTS = {
    "info_address": "Send the address or share a location pin:",
    "info_map_link": "Send a link or share a location pin:",
    "info_description": "Write any notes or details about the party:",
}

# Calendar ID to namespace callback data
CALENDAR_ID = 1

# Conversation states
TYPING_INFO_VALUE = 0
PICKING_DATE = 1
PICKING_TIME = 2


def _calendar_markup(json_str: str) -> InlineKeyboardMarkup:
    """Convert the JSON string from python-telegram-bot-calendar to InlineKeyboardMarkup."""
    data = json.loads(json_str)
    rows = []
    for row in data["inline_keyboard"]:
        rows.append([
            InlineKeyboardButton(
                text=btn["text"],
                callback_data=btn.get("callback_data"),
            )
            for btn in row
        ])
    return InlineKeyboardMarkup(rows)


def _new_calendar():
    """Create a fresh WMonthTelegramCalendar starting from today."""
    return WMonthTelegramCalendar(calendar_id=CALENDAR_ID, min_date=date.today())


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


# --------------- Debounced info-change notifications ---------------

NOTIFICATION_DELAY = 30  # seconds — changes within this window are batched


def _schedule_info_notification(
    context: ContextTypes.DEFAULT_TYPE, party_id: int, admin_id: int,
) -> None:
    """Schedule (or reschedule) a debounced notification for party info changes.

    Every call resets the 30-second timer so rapid edits produce only one message.
    """
    job_name = f"info_notify_{party_id}"
    # Cancel any pending notification for this party (resets the timer)
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()
    # Schedule a new one
    context.job_queue.run_once(
        _send_info_notification,
        when=NOTIFICATION_DELAY,
        data={"party_id": party_id, "admin_id": admin_id},
        name=job_name,
    )


async def _send_info_notification(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job callback: notify all party members (except the admin) about info changes."""
    data = context.job.data
    party_id = data["party_id"]
    admin_id = data["admin_id"]

    party = await db.get_party_by_id(party_id)
    if party is None:
        return  # Party was deleted before notification fired

    info = await db.get_party_info(party_id) or {}
    members = await db.get_members(party_id)

    text = (
        f"📢 <b>Party info has been updated!</b>\n\n"
        + _build_info_text(party["name"], info)
    )

    for m in members:
        if m["telegram_id"] == admin_id:
            continue
        try:
            await context.bot.send_message(
                chat_id=m["telegram_id"],
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception:
            logger.debug("Could not notify user %s", m["telegram_id"])


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

    # Date & time: show inline calendar
    if field == "info_datetime":
        cal_json, step = _new_calendar().build()
        text = f"🕐 <b>Date & time</b>\n\n"
        if current:
            text += f"Current: {esc(current)}\n\n"
        text += f"Select the {LSTEP[step]}:"
        await query.edit_message_text(
            text, parse_mode="HTML", reply_markup=_calendar_markup(cal_json),
        )
        return PICKING_DATE

    # Other fields: show text prompt
    prompt = FIELD_PROMPTS.get(field, "Type the new value:")
    text = f"✏️ <b>{label}</b>\n\n"
    if current:
        text += f"Current: {esc(current)}\n\n"
    text += prompt

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=edit_info_field_keyboard(party_id, field, bool(current)),
    )
    return TYPING_INFO_VALUE


# --------------- Calendar date picking ---------------

async def handle_calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process inline calendar button presses."""
    query = update.callback_query
    await query.answer()

    result, key, step = _new_calendar().process(query.data)

    party_id = context.user_data.get("edit_info_party_id")

    if not result and key:
        # User navigated to a different month/year — update the calendar
        await query.edit_message_text(
            f"🕐 <b>Date & time</b>\n\nSelect the {LSTEP[step]}:",
            parse_mode="HTML",
            reply_markup=_calendar_markup(key),
        )
        return PICKING_DATE

    if result:
        # User picked a date — save it and show time picker
        context.user_data["edit_info_date"] = result
        await query.edit_message_text(
            f"🕐 <b>Date & time</b>\n\n"
            f"Date: <b>{result.strftime('%b %d, %Y')}</b>\n\n"
            "Now pick the time:",
            parse_mode="HTML",
            reply_markup=time_picker_keyboard(party_id),
        )
        return PICKING_TIME

    # No-op button (e.g. blank cells) — stay in same state
    return PICKING_DATE


# --------------- Time picking ---------------

async def handle_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process time button press, save datetime, return to edit menu."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    party_id = int(parts[1])
    hour = int(parts[2])
    minute = int(parts[3])

    picked_date = context.user_data.get("edit_info_date")
    if picked_date is None:
        await query.edit_message_text("Something went wrong. Please try again.")
        return ConversationHandler.END

    return await _save_datetime(
        party_id, picked_date, hour, minute,
        send_func=lambda text, **kw: query.edit_message_text(text, **kw),
        context=context,
        admin_id=update.effective_user.id,
    )


async def handle_time_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Navigate between time picker pages."""
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    party_id = int(parts[1])
    page = int(parts[2])

    picked_date = context.user_data.get("edit_info_date")
    date_str = picked_date.strftime('%b %d, %Y') if picked_date else "?"

    await query.edit_message_text(
        f"🕐 <b>Date & time</b>\n\n"
        f"Date: <b>{date_str}</b>\n\n"
        "Now pick the time:",
        parse_mode="HTML",
        reply_markup=time_picker_keyboard(party_id, page=page),
    )
    return PICKING_TIME


async def receive_time_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Accept a typed time like '18:30', '18.30', '1830' while in PICKING_TIME state."""
    party_id = context.user_data.get("edit_info_party_id")
    picked_date = context.user_data.get("edit_info_date")

    if picked_date is None:
        await update.message.reply_text("Something went wrong. Please try again.")
        return ConversationHandler.END

    raw = update.message.text.strip()

    # Try parsing common time formats: "18:30", "18.30", "1830", "18 30"
    m = re.match(r"^(\d{1,2})[:.\s]?(\d{2})$", raw)
    if not m:
        await update.message.reply_text(
            "⚠️ Couldn't parse that time. Use the buttons above, or type like <b>18:30</b>.",
            parse_mode="HTML",
            reply_markup=time_picker_keyboard(party_id),
        )
        return PICKING_TIME

    hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        await update.message.reply_text(
            "⚠️ Invalid time. Hours 0–23, minutes 0–59. Try again.",
            reply_markup=time_picker_keyboard(party_id),
        )
        return PICKING_TIME

    return await _save_datetime(
        party_id, picked_date, hour, minute,
        send_func=lambda text, **kw: update.message.reply_text(text, **kw),
        context=context,
        admin_id=update.effective_user.id,
    )


async def receive_date_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text typed while the inline calendar is showing."""
    await update.message.reply_text(
        "Please use the calendar buttons above to pick a date.",
    )
    return PICKING_DATE


async def _save_datetime(party_id, picked_date, hour, minute, *, send_func, context, admin_id) -> int:
    """Save the datetime and show confirmation. Shared by button and text handlers."""
    value = f"{picked_date.strftime('%b %d, %Y')} at {hour:02d}:{minute:02d}"
    await db.update_party_info(party_id, "info_datetime", value)

    party = await db.get_party_by_id(party_id)
    if party is None:
        await send_func("Party not found.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END
    info = await db.get_party_info(party_id) or {}

    _schedule_info_notification(context, party_id, admin_id)

    await send_func(
        f"✅ Date & time set!\n\n" + _build_info_text(party["name"], info),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=edit_info_keyboard(party_id, info),
    )
    return ConversationHandler.END


# --------------- Text input ---------------

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

    _schedule_info_notification(context, party_id, user.id)

    await update.message.reply_text(
        f"✅ {label} updated!\n\n" + _build_info_text(party["name"], info),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=edit_info_keyboard(party_id, info),
    )
    return ConversationHandler.END


# --------------- Location input ---------------

async def receive_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle a shared location pin — save as Google Maps link."""
    party_id = context.user_data.get("edit_info_party_id")
    field = context.user_data.get("edit_info_field")
    user = update.effective_user

    if not await db.is_user_admin(party_id, user.id):
        await update.message.reply_text("You don't have permission to do this.")
        return ConversationHandler.END

    # Only accept locations for address and map link fields
    if field not in ("info_address", "info_map_link"):
        await update.message.reply_text(
            "📍 Location pins aren't supported for this field. Please type text instead.",
            reply_markup=edit_info_field_keyboard(party_id, field, False),
        )
        return TYPING_INFO_VALUE

    loc = update.message.location
    maps_url = f"https://www.google.com/maps?q={loc.latitude},{loc.longitude}"

    # Save the map link
    await db.update_party_info(party_id, "info_map_link", maps_url)

    party = await db.get_party_by_id(party_id)
    if party is None:
        await update.message.reply_text("Party not found.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END
    info = await db.get_party_info(party_id) or {}

    _schedule_info_notification(context, party_id, user.id)

    # If we were editing the address field, prompt to also type the address text
    if field == "info_address":
        await update.message.reply_text(
            f"✅ Map link saved!\n\n"
            "Now type the address text (street, building, etc.) or cancel:",
            parse_mode="HTML",
            reply_markup=edit_info_field_keyboard(party_id, field, False),
        )
        return TYPING_INFO_VALUE

    # Editing map link — done
    await update.message.reply_text(
        f"✅ Map link saved!\n\n" + _build_info_text(party["name"], info),
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=edit_info_keyboard(party_id, info),
    )
    return ConversationHandler.END


# --------------- Cancel / fallbacks ---------------

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

    _schedule_info_notification(context, party_id, user.id)

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
                MessageHandler(filters.LOCATION, receive_location),
            ],
            PICKING_DATE: [
                CallbackQueryHandler(handle_calendar_callback, pattern=r"^cbcal_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_date_text),
            ],
            PICKING_TIME: [
                CallbackQueryHandler(handle_time_callback, pattern=r"^pick_time:\d+:\d+:\d+$"),
                CallbackQueryHandler(handle_time_page, pattern=r"^time_page:\d+:\d+$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_time_text),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(clear_info_callback, pattern=r"^clear_info:\d+:info_\w+$"),
            CallbackQueryHandler(cancel_set_info, pattern=r"^edit_party_info:\d+$"),
        ],
        per_message=False,
        allow_reentry=True,
    )
