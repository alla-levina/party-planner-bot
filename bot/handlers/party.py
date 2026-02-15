"""Handlers for creating a party, opening a party menu, and invite links."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

logger = logging.getLogger(__name__)

from bot import database as db
from bot.keyboards import (
    cancel_keyboard,
    confirm_cancel_party_keyboard,
    confirm_leave_keyboard,
    invite_keyboard,
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

    # Refresh display name if it changed (username update, etc.)
    display = user_display_name(user)
    if member["telegram_name"] != display:
        await db.update_member_name(party_id, user.id, display)

    is_admin = bool(member.get("is_admin"))
    is_owner = party["creator_id"] == user.id

    fillings = await db.get_fillings(party_id)
    members = await db.get_members(party_id)

    await query.edit_message_text(
        f"🎉 <b>{esc(party['name'])}</b>\n"
        f"Contributions: {len(fillings)}  |  Members: {len(members)}",
        parse_mode="HTML",
        reply_markup=party_menu_keyboard(party_id, is_admin=is_admin, is_owner=is_owner),
    )


async def invite_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the invite menu with link, share, and contact options."""
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
    link = f"https://t.me/{bot_info.username}?start={party['code']}"

    await query.edit_message_text(
        f"🔗 <b>Invite to {esc(party['name'])}</b>\n\n"
        f"Link: <a href=\"{esc(link)}\">{esc(link)}</a>\n\n"
        "Choose how to invite:",
        parse_mode="HTML",
        reply_markup=invite_keyboard(party_id, link),
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
        "All your contributions will be removed too.",
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
        f"This will permanently delete the party, all {len(fillings)} contribution(s) "
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
    members = await db.get_members(party_id)
    await db.delete_party(party_id)

    await query.edit_message_text(
        f"🚫 Party <b>{esc(party_name)}</b> has been cancelled and all data deleted.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )

    # Notify all other members that the party was cancelled
    for m in members:
        if m["telegram_id"] == user.id:
            continue
        try:
            await context.bot.send_message(
                chat_id=m["telegram_id"],
                text=f"🚫 Party <b>{esc(party_name)}</b> has been cancelled by the admin.",
                parse_mode="HTML",
            )
        except Exception:
            logger.debug("Could not notify user %s about cancellation", m["telegram_id"])


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


# --------------- Contact invite flow ---------------

WAITING_CONTACT = 10


def _cancel_invite_kb(party_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data=f"invite_link:{party_id}")],
    ])


def _after_invite_kb(party_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Invite more", callback_data=f"invite_link:{party_id}")],
        [InlineKeyboardButton("⬅️ Back to party", callback_data=f"open_party:{party_id}")],
    ])


async def add_contact_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the 'add contact' flow — ask user to share a contact card."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])

    user = update.effective_user
    member = await db.get_member(party_id, user.id)
    if member is None:
        await query.edit_message_text(
            "⚠️ You are no longer a member of this party.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    party = await db.get_party_by_id(party_id)
    if party is None:
        await query.edit_message_text("Party not found.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    context.user_data["invite_party_id"] = party_id

    await query.edit_message_text(
        "👤 <b>Add contact to the party</b>\n\n"
        "Share a contact using the 📎 attachment button.",
        parse_mode="HTML",
        reply_markup=_cancel_invite_kb(party_id),
    )
    return WAITING_CONTACT


async def receive_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle a shared contact — add them to the party."""
    party_id = context.user_data.get("invite_party_id")
    user = update.effective_user
    contact = update.message.contact

    party = await db.get_party_by_id(party_id)
    if party is None:
        await update.message.reply_text("Party not found.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    member = await db.get_member(party_id, user.id)
    if member is None:
        await update.message.reply_text(
            "⚠️ You are no longer a member of this party.",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    # Contact must have a Telegram user ID
    if not contact.user_id:
        await update.message.reply_text(
            "⚠️ This contact doesn't have a linked Telegram account.\n"
            "Share the invite link with them directly instead.",
            reply_markup=_after_invite_kb(party_id),
        )
        return ConversationHandler.END

    contact_id = contact.user_id

    # Can't invite yourself
    if contact_id == user.id:
        await update.message.reply_text(
            "😄 That's you! Share a different contact.",
            reply_markup=_cancel_invite_kb(party_id),
        )
        return WAITING_CONTACT

    # Try to get the actual Telegram profile (has username); fall back to contact card
    try:
        chat = await context.bot.get_chat(contact_id)
        if chat.username:
            contact_name = f"@{chat.username}"
        else:
            contact_name = chat.first_name or ""
            if chat.last_name:
                contact_name += f" {chat.last_name}"
            contact_name = contact_name.strip() or "Unknown"
    except Exception:
        contact_name = contact.first_name or ""
        if contact.last_name:
            contact_name += f" {contact.last_name}"
        contact_name = contact_name.strip() or "Unknown"

    # Check if already a member
    existing = await db.get_member(party_id, contact_id)
    if existing:
        await update.message.reply_text(
            f"👋 <b>{esc(contact_name)}</b> is already in this party!",
            parse_mode="HTML",
            reply_markup=_after_invite_kb(party_id),
        )
        return ConversationHandler.END

    # Add directly to the party
    await db.add_member(party_id, contact_id, contact_name)

    # Try to notify the added person
    try:
        await context.bot.send_message(
            chat_id=contact_id,
            text=(
                f"🎉 You've been added to <b>{esc(party['name'])}</b> "
                f"by {esc(user_display_name(user))}!"
            ),
            parse_mode="HTML",
        )
        await update.message.reply_text(
            f"✅ <b>{esc(contact_name)}</b> has been added and notified!",
            parse_mode="HTML",
            reply_markup=_after_invite_kb(party_id),
        )
    except Exception:
        await update.message.reply_text(
            f"✅ <b>{esc(contact_name)}</b> has been added to the party.\n\n"
            "⚠️ Couldn't notify them — they haven't started the bot yet. "
            "They'll see the party once they open the bot.",
            parse_mode="HTML",
            reply_markup=_after_invite_kb(party_id),
        )

    return ConversationHandler.END


async def _contact_wait_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle text typed while waiting for a contact card."""
    party_id = context.user_data.get("invite_party_id")
    await update.message.reply_text(
        "Please share a contact using the 📎 attachment button, or cancel.",
        reply_markup=_cancel_invite_kb(party_id),
    )
    return WAITING_CONTACT


async def cancel_invite_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the contact invite flow — return to invite menu."""
    query = update.callback_query
    await query.answer()
    party_id = context.user_data.get("invite_party_id")

    if party_id:
        party = await db.get_party_by_id(party_id)
        if party:
            bot_info = await context.bot.get_me()
            link = f"https://t.me/{bot_info.username}?start={party['code']}"
            await query.edit_message_text(
                f"🔗 <b>Invite to {esc(party['name'])}</b>\n\n"
                f"Link: <a href=\"{esc(link)}\">{esc(link)}</a>\n\n"
                "Choose how to invite:",
                parse_mode="HTML",
                reply_markup=invite_keyboard(party_id, link),
            )
            return ConversationHandler.END

    await query.edit_message_text("Cancelled.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def invite_contact_conversation() -> ConversationHandler:
    """Build the ConversationHandler for adding contacts to a party."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_contact_start, pattern=r"^add_contact:\d+$"),
        ],
        states={
            WAITING_CONTACT: [
                MessageHandler(filters.CONTACT, receive_contact),
                MessageHandler(filters.TEXT & ~filters.COMMAND, _contact_wait_text),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_invite_contact, pattern=r"^invite_link:\d+$"),
        ],
        per_message=False,
    )


# --------------- Broadcast message flow ---------------

TYPING_BROADCAST = 20


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Admin: start the broadcast flow — ask for message text."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])

    user = update.effective_user
    if not await db.is_user_admin(party_id, user.id):
        await query.edit_message_text("You don't have permission to do this.")
        return ConversationHandler.END

    party = await db.get_party_by_id(party_id)
    if party is None:
        await query.edit_message_text("Party not found.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    members = await db.get_members(party_id)
    recipient_count = sum(1 for m in members if m["telegram_id"] != user.id)

    if recipient_count == 0:
        is_owner = party["creator_id"] == user.id
        await query.edit_message_text(
            "There are no other members to send a message to.",
            reply_markup=party_menu_keyboard(party_id, is_admin=True, is_owner=is_owner),
        )
        return ConversationHandler.END

    context.user_data["broadcast_party_id"] = party_id

    await query.edit_message_text(
        f"📢 <b>Send message to {esc(party['name'])}</b>\n\n"
        f"Type the message to send to {recipient_count} member(s):",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return TYPING_BROADCAST


async def receive_broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive the broadcast text, send to all members, report results."""
    party_id = context.user_data.get("broadcast_party_id")
    user = update.effective_user

    if not await db.is_user_admin(party_id, user.id):
        await update.message.reply_text("You don't have permission to do this.")
        return ConversationHandler.END

    party = await db.get_party_by_id(party_id)
    if party is None:
        await update.message.reply_text("Party not found.", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

    text = update.message.text.strip()

    if not text:
        await update.message.reply_text(
            "Message can't be empty. Try again or cancel.",
            reply_markup=cancel_keyboard(),
        )
        return TYPING_BROADCAST

    if len(text) > 1000:
        await update.message.reply_text(
            "⚠️ Message is too long (max 1000 characters). Try shorter.",
            reply_markup=cancel_keyboard(),
        )
        return TYPING_BROADCAST

    members = await db.get_members(party_id)
    sender_name = user_display_name(user)

    broadcast_text = (
        f"📢 <b>Message from {esc(party['name'])}</b>\n\n"
        f"{esc(text)}\n\n"
        f"— {esc(sender_name)}"
    )

    sent = 0
    failed = 0
    for m in members:
        if m["telegram_id"] == user.id:
            continue
        try:
            await context.bot.send_message(
                chat_id=m["telegram_id"],
                text=broadcast_text,
                parse_mode="HTML",
            )
            sent += 1
        except Exception:
            failed += 1

    result = f"✅ Message sent to {sent} member(s)!"
    if failed:
        result += f"\n⚠️ {failed} member(s) couldn't be reached (they may have blocked the bot)."

    is_owner = party["creator_id"] == user.id
    await update.message.reply_text(
        result,
        reply_markup=party_menu_keyboard(party_id, is_admin=True, is_owner=is_owner),
    )
    return ConversationHandler.END


async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the broadcast flow — return to party menu."""
    query = update.callback_query
    await query.answer()
    party_id = context.user_data.get("broadcast_party_id")

    if party_id:
        party = await db.get_party_by_id(party_id)
        if party:
            is_owner = party["creator_id"] == update.effective_user.id
            await query.edit_message_text(
                "Cancelled.",
                reply_markup=party_menu_keyboard(party_id, is_admin=True, is_owner=is_owner),
            )
            return ConversationHandler.END

    await query.edit_message_text("Cancelled.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END


def broadcast_conversation() -> ConversationHandler:
    """Build the ConversationHandler for broadcasting messages to party members."""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(broadcast_start, pattern=r"^broadcast:\d+$"),
        ],
        states={
            TYPING_BROADCAST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_broadcast_text),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_broadcast, pattern=r"^cancel$"),
        ],
        per_message=False,
    )


# --------------- Conversations ---------------

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
