"""Handlers for viewing, adding, editing, and removing fillings."""

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
    cancel_keyboard,
    edit_filling_keyboard,
    fillings_list_keyboard,
    main_menu_keyboard,
    party_menu_keyboard,
    user_fillings_keyboard,
)
from bot.utils import esc, user_display_name

NOT_A_MEMBER_TEXT = "⚠️ You are no longer a member of this party."

# Conversation states
TYPING_FILLING_NAME = 0
TYPING_RENAME = 1


# --------------- View fillings ---------------

async def view_fillings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all fillings for the party."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])
    user = update.effective_user

    member = await db.get_member(party_id, user.id)
    if member is None:
        await query.edit_message_text(NOT_A_MEMBER_TEXT, reply_markup=main_menu_keyboard())
        return

    party = await db.get_party_by_id(party_id)
    fillings = await db.get_fillings(party_id)

    if not fillings:
        text = f"📜 <b>Fillings for {esc(party['name'])}</b>\n\nNo fillings yet — be the first to add one!"
    else:
        lines = [f"📜 <b>Fillings for {esc(party['name'])}</b>\n"]
        for i, f in enumerate(fillings, 1):
            lines.append(f"{i}. {esc(f['name'])}  — <i>{esc(f['added_by_name'])}</i>")
        text = "\n".join(lines)

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=fillings_list_keyboard(party_id),
    )


# --------------- Add filling (conversation) ---------------

async def add_filling_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt user to type filling name."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])
    user = update.effective_user

    member = await db.get_member(party_id, user.id)
    if member is None:
        await query.edit_message_text(NOT_A_MEMBER_TEXT, reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    context.user_data["add_filling_party_id"] = party_id

    await query.edit_message_text(
        "➕ <b>Add a filling</b>\n\nType the name of the filling you'd like to bring:",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return TYPING_FILLING_NAME


async def receive_filling_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the filling name, check for duplicates, save."""
    user = update.effective_user
    party_id = context.user_data.get("add_filling_party_id")

    # Membership check (user may have been kicked while typing)
    member = await db.get_member(party_id, user.id)
    if member is None:
        await update.message.reply_text(NOT_A_MEMBER_TEXT, reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    name = update.message.text.strip()

    if not name:
        await update.message.reply_text("Name can't be empty. Try again or cancel.",
                                        reply_markup=cancel_keyboard())
        return TYPING_FILLING_NAME

    if len(name) > 100:
        await update.message.reply_text(
            "⚠️ Name is too long (max 100 characters). Try a shorter name.",
            reply_markup=cancel_keyboard(),
        )
        return TYPING_FILLING_NAME

    # Duplicate check
    dup = await db.find_duplicate_filling(party_id, name)
    if dup:
        await update.message.reply_text(
            f"⚠️ <b>\"{esc(dup['name'])}\"</b> is already taken by <i>{esc(dup['added_by_name'])}</i>!\n"
            "Please pick a different filling.",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )
        return TYPING_FILLING_NAME

    display = user_display_name(user)
    await db.add_filling(party_id, name, user.id, display)

    await update.message.reply_text(
        f"✅ <b>{esc(name)}</b> was added!",
        parse_mode="HTML",
        reply_markup=party_menu_keyboard(party_id),
    )
    return ConversationHandler.END


async def cancel_add_filling(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    party_id = context.user_data.get("add_filling_party_id")
    if party_id:
        await query.edit_message_text("Cancelled.", reply_markup=party_menu_keyboard(party_id))
    else:
        await query.edit_message_text("Cancelled.")
    return ConversationHandler.END


# --------------- Edit fillings ---------------

async def edit_fillings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user's own fillings with edit buttons."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])
    user = update.effective_user

    member = await db.get_member(party_id, user.id)
    if member is None:
        await query.edit_message_text(NOT_A_MEMBER_TEXT, reply_markup=main_menu_keyboard())
        return

    fillings = await db.get_user_fillings(party_id, user.id)
    if not fillings:
        await query.edit_message_text(
            "You haven't added any fillings to this party yet.",
            reply_markup=party_menu_keyboard(party_id),
        )
        return

    await query.edit_message_text(
        "✏️ <b>Your fillings</b> — tap one to edit or remove:",
        parse_mode="HTML",
        reply_markup=user_fillings_keyboard(fillings, party_id),
    )


async def edit_one_filling_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show rename / remove options for a single filling."""
    query = update.callback_query
    await query.answer()
    filling_id = int(query.data.split(":")[1])

    filling = await db.get_filling_by_id(filling_id)
    if filling is None:
        await query.edit_message_text("Filling not found.")
        return

    user = update.effective_user
    member = await db.get_member(filling["party_id"], user.id)
    if member is None:
        await query.edit_message_text(NOT_A_MEMBER_TEXT, reply_markup=main_menu_keyboard())
        return

    # Only the filling's owner (or an admin) can edit it
    is_admin = bool(member.get("is_admin"))
    if filling["added_by_id"] != user.id and not is_admin:
        await query.edit_message_text("⚠️ You can only edit your own fillings.",
                                      reply_markup=party_menu_keyboard(filling["party_id"]))
        return

    await query.edit_message_text(
        f"Filling: <b>{esc(filling['name'])}</b>\n\nWhat would you like to do?",
        parse_mode="HTML",
        reply_markup=edit_filling_keyboard(filling_id, filling["party_id"]),
    )


# --------------- Remove filling ---------------

async def remove_filling_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a filling."""
    query = update.callback_query
    await query.answer()
    filling_id = int(query.data.split(":")[1])

    filling = await db.get_filling_by_id(filling_id)
    if filling is None:
        await query.edit_message_text("Filling not found.")
        return

    user = update.effective_user
    member = await db.get_member(filling["party_id"], user.id)
    if member is None:
        await query.edit_message_text(NOT_A_MEMBER_TEXT, reply_markup=main_menu_keyboard())
        return

    # Only the filling's owner (or an admin) can remove it
    is_admin = bool(member.get("is_admin"))
    if filling["added_by_id"] != user.id and not is_admin:
        await query.edit_message_text("⚠️ You can only remove your own fillings.",
                                      reply_markup=party_menu_keyboard(filling["party_id"]))
        return

    party_id = filling["party_id"]
    await db.delete_filling(filling_id)

    await query.edit_message_text(
        f"🗑 <b>{esc(filling['name'])}</b> removed.",
        parse_mode="HTML",
        reply_markup=party_menu_keyboard(party_id),
    )


# --------------- Rename filling (conversation) ---------------

async def rename_filling_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for new filling name."""
    query = update.callback_query
    await query.answer()
    filling_id = int(query.data.split(":")[1])

    filling = await db.get_filling_by_id(filling_id)
    if filling is None:
        await query.edit_message_text("Filling not found.")
        return ConversationHandler.END

    user = update.effective_user
    member = await db.get_member(filling["party_id"], user.id)
    if member is None:
        await query.edit_message_text(NOT_A_MEMBER_TEXT, reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    is_admin = bool(member.get("is_admin"))
    if filling["added_by_id"] != user.id and not is_admin:
        await query.edit_message_text("⚠️ You can only rename your own fillings.",
                                      reply_markup=party_menu_keyboard(filling["party_id"]))
        return ConversationHandler.END

    context.user_data["rename_filling_id"] = filling_id
    context.user_data["rename_filling_party_id"] = filling["party_id"]

    await query.edit_message_text(
        f"Current name: <b>{esc(filling['name'])}</b>\n\nType the new name:",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return TYPING_RENAME


async def receive_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Save the new filling name."""
    filling_id = context.user_data.get("rename_filling_id")
    party_id = context.user_data.get("rename_filling_party_id")
    user = update.effective_user

    member = await db.get_member(party_id, user.id)
    if member is None:
        await update.message.reply_text(NOT_A_MEMBER_TEXT, reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    new_name = update.message.text.strip()

    if not new_name:
        await update.message.reply_text("Name can't be empty. Try again or cancel.",
                                        reply_markup=cancel_keyboard())
        return TYPING_RENAME

    if len(new_name) > 100:
        await update.message.reply_text(
            "⚠️ Name is too long (max 100 characters). Try a shorter name.",
            reply_markup=cancel_keyboard(),
        )
        return TYPING_RENAME

    # Duplicate check
    dup = await db.find_duplicate_filling(party_id, new_name)
    if dup and dup["id"] != filling_id:
        await update.message.reply_text(
            f"⚠️ <b>\"{esc(dup['name'])}\"</b> is already taken by <i>{esc(dup['added_by_name'])}</i>!\n"
            "Please pick a different name.",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )
        return TYPING_RENAME

    await db.rename_filling(filling_id, new_name)

    await update.message.reply_text(
        f"✅ Filling renamed to <b>{esc(new_name)}</b>.",
        parse_mode="HTML",
        reply_markup=party_menu_keyboard(party_id),
    )
    return ConversationHandler.END


async def cancel_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    party_id = context.user_data.get("rename_filling_party_id")
    if party_id:
        await query.edit_message_text("Cancelled.", reply_markup=party_menu_keyboard(party_id))
    else:
        await query.edit_message_text("Cancelled.")
    return ConversationHandler.END


# --------------- Conversation builders ---------------

def add_filling_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_filling_start, pattern=r"^add_filling:\d+$"),
        ],
        states={
            TYPING_FILLING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_filling_name),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_add_filling, pattern=r"^cancel$"),
        ],
        per_message=False,
    )


def rename_filling_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(rename_filling_start, pattern=r"^rename_filling:\d+$"),
        ],
        states={
            TYPING_RENAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_rename),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_rename, pattern=r"^cancel$"),
        ],
        per_message=False,
    )
