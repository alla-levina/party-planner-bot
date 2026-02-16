"""Handlers for party ratings — admins send rating requests, members rate with stars."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot import database as db
from bot.keyboards import (
    after_rating_keyboard,
    confirm_send_ratings_keyboard,
    main_menu_keyboard,
    party_menu_keyboard,
    rating_stars_keyboard,
    ratings_view_keyboard,
)
from bot.utils import esc

logger = logging.getLogger(__name__)


def _star_display(rating: int) -> str:
    """Return a visual star string like ⭐⭐⭐☆☆ for a rating 1–5."""
    return "⭐" * rating + "☆" * (5 - rating)


# --------------- Admin: send rating request ---------------

async def rate_party_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: show confirmation before sending rating request to all members."""
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

    members = await db.get_members(party_id)
    count = len(members)

    await query.edit_message_text(
        f"⭐ <b>Rate the party — {esc(party['name'])}</b>\n\n"
        f"This will send a rating request to all {count} member(s).\n"
        "Each person can rate the party from 1 to 5 stars.",
        parse_mode="HTML",
        reply_markup=confirm_send_ratings_keyboard(party_id),
    )


async def confirm_send_ratings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: send rating request messages to all members."""
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

    members = await db.get_members(party_id)

    rating_text = (
        f"⭐ <b>How would you rate {esc(party['name'])}?</b>\n\n"
        "Tap to rate from 1 to 5 stars:"
    )

    sent = 0
    failed = 0
    for m in members:
        try:
            await context.bot.send_message(
                chat_id=m["telegram_id"],
                text=rating_text,
                parse_mode="HTML",
                reply_markup=rating_stars_keyboard(party_id),
            )
            sent += 1
        except Exception:
            failed += 1

    result = f"✅ Rating request sent to {sent} member(s)!"
    if failed:
        result += f"\n⚠️ {failed} member(s) couldn't be reached."

    is_owner = party["creator_id"] == user.id
    await query.edit_message_text(
        result,
        reply_markup=party_menu_keyboard(party_id, is_admin=True, is_owner=is_owner),
    )


# --------------- Member: submit a rating ---------------

async def handle_rating_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Member taps a star — save their rating."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    party_id = int(parts[1])
    rating = int(parts[2])

    if not 1 <= rating <= 5:
        return

    user = update.effective_user

    party = await db.get_party_by_id(party_id)
    if party is None:
        await query.edit_message_text("Party not found.")
        return

    member = await db.get_member(party_id, user.id)
    if member is None:
        await query.edit_message_text("⚠️ You are no longer a member of this party.")
        return

    await db.save_rating(party_id, user.id, rating)

    await query.edit_message_text(
        f"⭐ <b>{esc(party['name'])}</b>\n\n"
        f"Your rating: {_star_display(rating)} ({rating}/5)\n\n"
        "You can change your rating:",
        parse_mode="HTML",
        reply_markup=after_rating_keyboard(party_id),
    )


async def dismiss_rating_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove the rating keyboard after member is done."""
    query = update.callback_query
    await query.answer()
    party_id = int(query.data.split(":")[1])

    user = update.effective_user
    party = await db.get_party_by_id(party_id)
    rating_record = await db.get_user_rating(party_id, user.id)

    if party and rating_record:
        rating = rating_record["rating"]
        await query.edit_message_text(
            f"⭐ <b>{esc(party['name'])}</b>\n\n"
            f"Your rating: {_star_display(rating)} ({rating}/5)\n\n"
            "Thanks for rating!",
            parse_mode="HTML",
        )
    else:
        await query.edit_message_text("Thanks for rating!")


# --------------- View ratings ---------------

async def view_ratings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show party ratings to any member. Admins see individual ratings."""
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
        return

    party = await db.get_party_by_id(party_id)
    if party is None:
        await query.edit_message_text("Party not found.", reply_markup=main_menu_keyboard())
        return

    ratings = await db.get_ratings(party_id)

    if not ratings:
        await query.edit_message_text(
            f"📊 <b>Ratings for {esc(party['name'])}</b>\n\n"
            "No ratings yet.",
            parse_mode="HTML",
            reply_markup=ratings_view_keyboard(party_id),
        )
        return

    total = sum(r["rating"] for r in ratings)
    avg = total / len(ratings)
    avg_stars = round(avg)

    lines = [
        f"📊 <b>Ratings for {esc(party['name'])}</b>\n",
        f"{_star_display(avg_stars)} <b>{avg:.1f}</b>/5  ({len(ratings)} rating(s))\n",
    ]

    is_admin = bool(member.get("is_admin"))
    if is_admin and ratings:
        lines.append("")
        for r in ratings:
            lines.append(f"{_star_display(r['rating'])} — {esc(r['telegram_name'])}")

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=ratings_view_keyboard(party_id),
    )
