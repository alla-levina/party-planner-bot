"""Load configuration from environment / .env file."""

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. "
        "Create a .env file (see .env.example) with your Telegram bot token."
    )

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Add a PostgreSQL connection string to your .env file, e.g.:\n"
        "DATABASE_URL=postgresql://user:password@localhost:5432/maslenitsa"
    )
