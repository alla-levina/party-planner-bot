"""Handlers for /start, main menu, deep-link join, and 'my parties' list."""

from telegram import Update
from telegram.ext import ContextTypes

from bot import database as db
from bot.keyboards import main_menu_keyboard, parties_list_keyboard, party_menu_keyboard
from bot.utils import esc, user_display_name


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start with optional deep-link payload (party code)."""
    user = update.effective_user
    args = context.args  # deep-link payload

    if args:
        code = args[0]
        party = await db.get_party_by_code(code)
        if party is None:
            await update.message.reply_text(
                "😕 Party not found. The link may be invalid or expired.",
                reply_markup=main_menu_keyboard(),
            )
            return

        # Auto-join
        display = user_display_name(user)
        newly_joined = await db.add_member(party["id"], user.id, display)

        if newly_joined:
            text = f"🎉 Welcome to <b>{esc(party['name'])}</b>! You've joined the party."
        else:
            text = f"👋 You're already in <b>{esc(party['name'])}</b>!"

        is_admin = await db.is_user_admin(party["id"], user.id)
        is_owner = party["creator_id"] == user.id

        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=party_menu_keyboard(party["id"], is_admin=is_admin, is_owner=is_owner),
        )
        return

    # No deep-link → show main menu
    await update.message.reply_text(
        "🎉 <b>Welcome to Party Planner Bot!</b>\n\n"
        "Create a party and invite friends to coordinate who brings what "
        "— so nobody brings the same thing.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show main menu (from inline button)."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎉 <b>Party Planner Bot</b>\n\nWhat would you like to do?",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


async def parties_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /parties command — show user's parties."""
    user = update.effective_user
    parties = await db.get_parties_for_user(user.id)
    if not parties:
        await update.message.reply_text(
            "You haven't joined any parties yet.\n"
            "Create one or ask a friend for an invite link!",
            reply_markup=main_menu_keyboard(),
        )
        return

    await update.message.reply_text(
        "📋 <b>Your parties:</b>",
        parse_mode="HTML",
        reply_markup=parties_list_keyboard(parties, user.id),
    )


async def my_parties_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show list of parties the user belongs to (from inline button)."""
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    parties = await db.get_parties_for_user(user.id)
    if not parties:
        await query.edit_message_text(
            "You haven't joined any parties yet.\n"
            "Create one or ask a friend for an invite link!",
            reply_markup=main_menu_keyboard(),
        )
        return

    await query.edit_message_text(
        "📋 <b>Your parties:</b>",
        parse_mode="HTML",
        reply_markup=parties_list_keyboard(parties, user.id),
    )
