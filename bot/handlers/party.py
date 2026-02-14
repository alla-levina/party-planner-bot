"""Handlers for creating a party, opening a party menu, and invite links."""

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
    confirm_cancel_party_keyboard,
    confirm_leave_keyboard,
    main_menu_keyboard,
    party_menu_keyboard,
)
from bot.utils import esc, generate_party_code, user_display_name


# Conversation states
TYPING_PARTY_NAME = 0


async def create_party_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Begin the 'create party' conversation — ask for the party name."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎉 <b>Create a new party</b>\n\nSend me the name for your party:",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return TYPING_PARTY_NAME


async def receive_party_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the party name, create the party, auto-join creator."""
    user = update.effective_user
    name = update.message.text.strip()

    if not name:
        await update.message.reply_text("Name can't be empty. Try again or cancel.",
                                        reply_markup=cancel_keyboard())
        return TYPING_PARTY_NAME

    if len(name) > 100:
        await update.message.reply_text(
            "⚠️ Name is too long (max 100 characters). Try a shorter name.",
            reply_markup=cancel_keyboard(),
        )
        return TYPING_PARTY_NAME

    if await db.has_party_with_name(user.id, name):
        await update.message.reply_text(
            f"⚠️ You already have a party called <b>{esc(name)}</b>.\n"
            "Please pick a different name.",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )
        return TYPING_PARTY_NAME

    code = generate_party_code()
    party_id = await db.create_party(name, code, user.id)

    # Auto-add creator as a member + admin
    display = user_display_name(user)
    await db.add_member(party_id, user.id, display, is_admin=True)

    bot_info = await context.bot.get_me()
    invite_link = f"https://t.me/{bot_info.username}?start={code}"

    await update.message.reply_text(
        f"🎉 Party <b>{esc(name)}</b> created!\n\n"
        f"Share this link with your guests:\n<a href=\"{esc(invite_link)}\">{esc(invite_link)}</a>",
        parse_mode="HTML",
        reply_markup=party_menu_keyboard(party_id, is_admin=True, is_owner=True),
    )
    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel any active conversation and return to main menu."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Cancelled.",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


# --- Non-conversation callbacks ---

async def open_party_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Open a party's menu."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])

    party = await db.get_party_by_id(party_id)
    if party is None:
        await query.edit_message_text("Party not found.", reply_markup=main_menu_keyboard())
        return

    user = update.effective_user
    member = await db.get_member(party_id, user.id)
    if member is None:
        await query.edit_message_text(
            "⚠️ You are no longer a member of this party.",
            reply_markup=main_menu_keyboard(),
        )
        return

    is_admin = bool(member.get("is_admin"))
    is_owner = party["creator_id"] == user.id

    fillings = await db.get_fillings(party_id)
    members = await db.get_members(party_id)

    await query.edit_message_text(
        f"🎉 <b>{esc(party['name'])}</b>\n"
        f"Items: {len(fillings)}  |  Members: {len(members)}",
        parse_mode="HTML",
        reply_markup=party_menu_keyboard(party_id, is_admin=is_admin, is_owner=is_owner),
    )


async def invite_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the invite link for a party."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])

    party = await db.get_party_by_id(party_id)
    if party is None:
        await query.edit_message_text("Party not found.", reply_markup=main_menu_keyboard())
        return

    user = update.effective_user
    member = await db.get_member(party_id, user.id)
    if member is None:
        await query.edit_message_text(
            "⚠️ You are no longer a member of this party.",
            reply_markup=main_menu_keyboard(),
        )
        return

    bot_info = await context.bot.get_me()
    invite_link = f"https://t.me/{bot_info.username}?start={party['code']}"

    is_admin = bool(member.get("is_admin"))
    is_owner = party["creator_id"] == user.id

    await query.edit_message_text(
        f"🔗 <b>Invite link for {esc(party['name'])}</b>\n\n"
        f"Share this link:\n<a href=\"{esc(invite_link)}\">{esc(invite_link)}</a>",
        parse_mode="HTML",
        reply_markup=party_menu_keyboard(party_id, is_admin=is_admin, is_owner=is_owner),
    )


async def leave_party_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ask for confirmation before leaving a party."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])

    party = await db.get_party_by_id(party_id)
    if party is None:
        await query.edit_message_text("Party not found.", reply_markup=main_menu_keyboard())
        return

    user = update.effective_user

    member = await db.get_member(party_id, user.id)
    if member is None:
        await query.edit_message_text(
            "⚠️ You are no longer a member of this party.",
            reply_markup=main_menu_keyboard(),
        )
        return

    # Prevent the owner from leaving their own party
    if party["creator_id"] == user.id:
        await query.edit_message_text(
            "⚠️ You are the owner of this party and cannot leave it.\n"
            "Use \"Cancel party\" if you want to delete it.",
            reply_markup=party_menu_keyboard(party_id, is_admin=True, is_owner=True),
        )
        return

    await query.edit_message_text(
        f"🚪 Are you sure you want to leave <b>{esc(party['name'])}</b>?\n\n"
        "All your items will be removed too.",
        parse_mode="HTML",
        reply_markup=confirm_leave_keyboard(party_id),
    )


async def cancel_party_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: ask confirmation before cancelling a party."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])

    party = await db.get_party_by_id(party_id)
    user = update.effective_user

    if party is None or not await db.is_user_admin(party_id, user.id):
        await query.edit_message_text("You don't have permission to do this.")
        return

    members = await db.get_members(party_id)
    fillings = await db.get_fillings(party_id)

    await query.edit_message_text(
        f"🚫 Are you sure you want to <b>cancel</b> the party <b>{esc(party['name'])}</b>?\n\n"
        f"This will permanently delete the party, all {len(fillings)} item(s) "
        f"and remove all {len(members)} member(s).\n\n"
        "⚠️ This cannot be undone!",
        parse_mode="HTML",
        reply_markup=confirm_cancel_party_keyboard(party_id),
    )


async def confirm_cancel_party_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: actually delete the party after confirmation."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])

    party = await db.get_party_by_id(party_id)
    user = update.effective_user

    if party is None or not await db.is_user_admin(party_id, user.id):
        await query.edit_message_text("You don't have permission to do this.")
        return

    party_name = party["name"]
    await db.delete_party(party_id)

    await query.edit_message_text(
        f"🚫 Party <b>{esc(party_name)}</b> has been cancelled and all data deleted.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def confirm_leave_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Actually leave the party after confirmation."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])

    party = await db.get_party_by_id(party_id)
    if party is None:
        await query.edit_message_text("Party not found.", reply_markup=main_menu_keyboard())
        return

    user = update.effective_user

    # Re-check: owner cannot leave
    if party["creator_id"] == user.id:
        await query.edit_message_text(
            "⚠️ You are the owner of this party and cannot leave it.",
            reply_markup=party_menu_keyboard(party_id, is_admin=True, is_owner=True),
        )
        return

    await db.remove_member(party_id, user.id)

    await query.edit_message_text(
        f"👋 You have left <b>{esc(party['name'])}</b>.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


def create_party_conversation() -> ConversationHandler:
    """Build the ConversationHandler for party creation."""
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(create_party_start, pattern=r"^create_party$")],
        states={
            TYPING_PARTY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_party_name),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation, pattern=r"^cancel$"),
        ],
        per_message=False,
    )
