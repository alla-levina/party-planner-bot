"""Handlers for viewing and searching party members."""

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
    admin_members_keyboard,
    cancel_keyboard,
    confirm_kick_keyboard,
    main_menu_keyboard,
    members_keyboard,
    party_menu_keyboard,
)
from bot.utils import esc

NOT_A_MEMBER_TEXT = "⚠️ You are no longer a member of this party."

# Conversation state
TYPING_SEARCH = 0


async def members_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show all members of a party. Admin sees manage buttons."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])

    party = await db.get_party_by_id(party_id)
    user = update.effective_user

    member = await db.get_member(party_id, user.id)
    if member is None:
        await query.edit_message_text(NOT_A_MEMBER_TEXT, reply_markup=main_menu_keyboard())
        return

    members = await db.get_members(party_id)
    is_admin = bool(member.get("is_admin"))

    if not members:
        text = f"👥 <b>Members of {esc(party['name'])}</b>\n\nNo members yet."
    else:
        lines = [f"👥 <b>Members of {esc(party['name'])}</b>\n"]
        for i, m in enumerate(members, 1):
            badge = ""
            if m["telegram_id"] == party["creator_id"]:
                badge = " 👑"
            elif m.get("is_admin"):
                badge = " ⭐️"
            lines.append(f"{i}. {esc(m['telegram_name'])}{badge}")
        if is_admin:
            lines.append("\n👑 = owner  ⭐️ = admin\n⬆️ promote  ⬇️ demote  ❌ remove")
        text = "\n".join(lines)

    if is_admin and len(members) > 1:
        keyboard = admin_members_keyboard(members, party_id, user.id)
    else:
        keyboard = members_keyboard(party_id)

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def kick_member_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: ask confirmation before removing a member."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    party_id = int(parts[1])
    target_id = int(parts[2])

    party = await db.get_party_by_id(party_id)
    user = update.effective_user

    if party is None or not await db.is_user_admin(party_id, user.id):
        await query.edit_message_text("You don't have permission to do this.")
        return

    # Cannot kick the party owner
    if target_id == party["creator_id"]:
        await query.edit_message_text(
            "⚠️ You cannot remove the party owner.",
            reply_markup=members_keyboard(party_id),
        )
        return

    member = await db.get_member(party_id, target_id)
    if member is None:
        await query.edit_message_text("Member not found.", reply_markup=members_keyboard(party_id))
        return

    await query.edit_message_text(
        f"Are you sure you want to remove <b>{esc(member['telegram_name'])}</b> "
        f"from <b>{esc(party['name'])}</b>?\n\n"
        "All their contributions will be removed too.",
        parse_mode="HTML",
        reply_markup=confirm_kick_keyboard(party_id, target_id),
    )


async def confirm_kick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: actually remove the member after confirmation."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    party_id = int(parts[1])
    target_id = int(parts[2])

    party = await db.get_party_by_id(party_id)
    user = update.effective_user

    if party is None or not await db.is_user_admin(party_id, user.id):
        await query.edit_message_text("You don't have permission to do this.")
        return

    # Re-check: cannot kick the owner
    if target_id == party["creator_id"]:
        await query.edit_message_text(
            "⚠️ You cannot remove the party owner.",
            reply_markup=members_keyboard(party_id),
        )
        return

    member = await db.get_member(party_id, target_id)
    name = member["telegram_name"] if member else "Unknown"

    await db.remove_member(party_id, target_id)

    # Notify the kicked user
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"🚪 You have been removed from the party <b>{esc(party['name'])}</b> by an admin.\n"
                 "All your contributions have been removed.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
    except Exception:
        pass  # User may have blocked the bot

    await query.edit_message_text(
        f"🗑 <b>{esc(name)}</b> has been removed from the party.",
        parse_mode="HTML",
        reply_markup=members_keyboard(party_id),
    )


async def promote_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: promote a member to admin."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    party_id = int(parts[1])
    target_id = int(parts[2])

    party = await db.get_party_by_id(party_id)
    user = update.effective_user

    if party is None or not await db.is_user_admin(party_id, user.id):
        await query.edit_message_text("You don't have permission to do this.")
        return

    member = await db.get_member(party_id, target_id)
    if member is None:
        await query.edit_message_text("Member not found.", reply_markup=members_keyboard(party_id))
        return

    await db.promote_admin(party_id, target_id)

    await query.edit_message_text(
        f"⭐️ <b>{esc(member['telegram_name'])}</b> is now an admin!",
        parse_mode="HTML",
        reply_markup=members_keyboard(party_id),
    )


async def demote_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: remove admin role from a member."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    party_id = int(parts[1])
    target_id = int(parts[2])

    party = await db.get_party_by_id(party_id)
    user = update.effective_user

    if party is None or not await db.is_user_admin(party_id, user.id):
        await query.edit_message_text("You don't have permission to do this.")
        return

    # Cannot demote the party owner
    if target_id == party["creator_id"]:
        await query.edit_message_text(
            "⚠️ You cannot demote the party owner.",
            reply_markup=members_keyboard(party_id),
        )
        return

    member = await db.get_member(party_id, target_id)
    if member is None:
        await query.edit_message_text("Member not found.", reply_markup=members_keyboard(party_id))
        return

    await db.demote_admin(party_id, target_id)

    await query.edit_message_text(
        f"<b>{esc(member['telegram_name'])}</b> is no longer an admin.",
        parse_mode="HTML",
        reply_markup=members_keyboard(party_id),
    )


# --------------- Search members (conversation) ---------------

async def search_member_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for search query."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])
    context.user_data["search_member_party_id"] = party_id

    await query.edit_message_text(
        "🔍 <b>Search members</b>\n\nType a name or username to search:",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return TYPING_SEARCH


async def receive_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Search members and show results."""
    party_id = context.user_data.get("search_member_party_id")
    query_text = update.message.text.strip()

    if not query_text:
        await update.message.reply_text("Please type something to search.",
                                        reply_markup=cancel_keyboard())
        return TYPING_SEARCH

    results = await db.search_members(party_id, query_text)

    if not results:
        text = f"No members found matching \"{esc(query_text)}\"."
    else:
        lines = [f"🔍 <b>Search results for \"{esc(query_text)}\":</b>\n"]
        for i, m in enumerate(results, 1):
            lines.append(f"{i}. {esc(m['telegram_name'])}")
        text = "\n".join(lines)

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=members_keyboard(party_id),
    )
    return ConversationHandler.END


async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    party_id = context.user_data.get("search_member_party_id")
    if party_id:
        await query.edit_message_text("Cancelled.", reply_markup=party_menu_keyboard(party_id))
    else:
        await query.edit_message_text("Cancelled.")
    return ConversationHandler.END


def search_member_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(search_member_start, pattern=r"^search_member:\d+$"),
        ],
        states={
            TYPING_SEARCH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_search_query),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_search, pattern=r"^cancel$"),
        ],
        per_message=False,
    )
