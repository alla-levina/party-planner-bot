"""Entry point – build the Application, register handlers, start polling."""

import logging

from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler

from bot.config import BOT_TOKEN, DATABASE_URL
from bot import database as db
from bot.handlers.start import start_command, main_menu_callback, my_parties_callback
from bot.handlers.party import (
    cancel_party_callback,
    confirm_cancel_party_callback,
    confirm_leave_callback,
    create_party_conversation,
    leave_party_callback,
    open_party_callback,
    invite_link_callback,
)
from bot.handlers.fillings import (
    add_filling_conversation,
    rename_filling_conversation,
    view_fillings_callback,
    edit_fillings_callback,
    edit_one_filling_callback,
    remove_filling_callback,
)
from bot.handlers.members import (
    confirm_kick_callback,
    demote_admin_callback,
    kick_member_callback,
    promote_admin_callback,
    search_member_conversation,
    members_callback,
)
from bot.handlers.party_info import (
    clear_info_callback,
    edit_party_info_callback,
    party_info_callback,
    set_info_conversation,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Build and run the bot."""
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # --- Conversation handlers (must be added before plain callback handlers) ---
    app.add_handler(create_party_conversation())
    app.add_handler(add_filling_conversation())
    app.add_handler(rename_filling_conversation())
    app.add_handler(search_member_conversation())
    app.add_handler(set_info_conversation())

    # --- Command handlers ---
    app.add_handler(CommandHandler("start", start_command))

    # --- Callback query handlers ---
    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern=r"^main_menu$"))
    app.add_handler(CallbackQueryHandler(my_parties_callback, pattern=r"^my_parties$"))
    app.add_handler(CallbackQueryHandler(open_party_callback, pattern=r"^open_party:\d+$"))
    app.add_handler(CallbackQueryHandler(invite_link_callback, pattern=r"^invite_link:\d+$"))
    app.add_handler(CallbackQueryHandler(view_fillings_callback, pattern=r"^view_fillings:\d+$"))
    app.add_handler(CallbackQueryHandler(edit_fillings_callback, pattern=r"^edit_fillings:\d+$"))
    app.add_handler(CallbackQueryHandler(edit_one_filling_callback, pattern=r"^edit_one_filling:\d+$"))
    app.add_handler(CallbackQueryHandler(remove_filling_callback, pattern=r"^remove_filling:\d+$"))
    app.add_handler(CallbackQueryHandler(members_callback, pattern=r"^members:\d+$"))
    app.add_handler(CallbackQueryHandler(leave_party_callback, pattern=r"^leave_party:\d+$"))
    app.add_handler(CallbackQueryHandler(confirm_leave_callback, pattern=r"^confirm_leave:\d+$"))
    app.add_handler(CallbackQueryHandler(cancel_party_callback, pattern=r"^cancel_party:\d+$"))
    app.add_handler(CallbackQueryHandler(confirm_cancel_party_callback, pattern=r"^confirm_cancel_party:\d+$"))
    app.add_handler(CallbackQueryHandler(kick_member_callback, pattern=r"^kick_member:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(confirm_kick_callback, pattern=r"^confirm_kick:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(promote_admin_callback, pattern=r"^promote_admin:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(demote_admin_callback, pattern=r"^demote_admin:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(party_info_callback, pattern=r"^party_info:\d+$"))
    app.add_handler(CallbackQueryHandler(edit_party_info_callback, pattern=r"^edit_party_info:\d+$"))
    app.add_handler(CallbackQueryHandler(clear_info_callback, pattern=r"^clear_info:\d+:info_\w+$"))

    # --- Init DB on startup, close on shutdown ---
    async def post_init(application) -> None:
        await db.init_db(DATABASE_URL)
        logger.info("Database initialised.")

    async def post_shutdown(application) -> None:
        await db.close_db()
        logger.info("Database pool closed.")

    app.post_init = post_init
    app.post_shutdown = post_shutdown

    logger.info("Starting bot…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
