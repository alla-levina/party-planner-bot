"""Utility helpers."""

import html
import secrets
import string


def esc(text: str) -> str:
    """Escape text for Telegram HTML parse mode."""
    return html.escape(str(text))


def generate_party_code(length: int = 8) -> str:
    """Generate a URL-safe random code for a party invite link."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def user_display_name(user) -> str:
    """Build a readable display name from a telegram User object."""
    if user.username:
        return f"@{user.username}"
    full = user.first_name or ""
    if user.last_name:
        full += f" {user.last_name}"
    return full.strip() or "Anonymous"
