"""Load configuration from environment / .env file."""

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. "
        "Create a .env file (see .env.example) with your Telegram bot token."
    )
