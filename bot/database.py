"""Database layer – SQLite via aiosqlite."""

import aiosqlite
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "bot.db")


async def init_db() -> None:
    """Create tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS parties (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                code        TEXT    NOT NULL UNIQUE,
                creator_id  INTEGER NOT NULL,
                created_at  TEXT    NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS fillings (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                party_id      INTEGER NOT NULL,
                name          TEXT    NOT NULL,
                added_by_id   INTEGER NOT NULL,
                added_by_name TEXT    NOT NULL,
                created_at    TEXT    NOT NULL,
                FOREIGN KEY (party_id) REFERENCES parties(id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS party_members (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                party_id       INTEGER NOT NULL,
                telegram_id    INTEGER NOT NULL,
                telegram_name  TEXT    NOT NULL,
                joined_at      TEXT    NOT NULL,
                FOREIGN KEY (party_id) REFERENCES parties(id),
                UNIQUE(party_id, telegram_id)
            )
            """
        )
        # Migration: add is_admin column if missing (for existing databases)
        try:
            await db.execute(
                "ALTER TABLE party_members ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass  # column already exists

        # Back-fill: ensure party creators are marked as admin
        await db.execute(
            """
            UPDATE party_members SET is_admin = 1
            WHERE is_admin = 0 AND EXISTS (
                SELECT 1 FROM parties
                WHERE parties.id = party_members.party_id
                  AND parties.creator_id = party_members.telegram_id
            )
            """
        )

        await db.commit()


# --------------- Party CRUD ---------------

async def has_party_with_name(creator_id: int, name: str) -> bool:
    """Check if a creator already owns an active party with this name (case-insensitive)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT 1 FROM parties WHERE creator_id = ? AND LOWER(name) = LOWER(?) LIMIT 1",
            (creator_id, name),
        )
        return await cursor.fetchone() is not None


async def create_party(name: str, code: str, creator_id: int) -> int:
    """Create a party and return its id."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO parties (name, code, creator_id, created_at) VALUES (?, ?, ?, ?)",
            (name, code, creator_id, datetime.utcnow().isoformat()),
        )
        await db.commit()
        return cursor.lastrowid


async def get_party_by_code(code: str) -> dict | None:
    """Look up a party by its unique invite code."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM parties WHERE code = ?", (code,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_party_by_id(party_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM parties WHERE id = ?", (party_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_parties_for_user(telegram_id: int) -> list[dict]:
    """Return all parties a user belongs to, including the creator's display name."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT p.*, creator_pm.telegram_name AS creator_name
            FROM parties p
            JOIN party_members pm ON p.id = pm.party_id
            LEFT JOIN party_members creator_pm
                ON p.id = creator_pm.party_id AND p.creator_id = creator_pm.telegram_id
            WHERE pm.telegram_id = ?
            ORDER BY p.created_at DESC
            """,
            (telegram_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# --------------- Members CRUD ---------------

async def add_member(party_id: int, telegram_id: int, telegram_name: str, is_admin: bool = False) -> bool:
    """Add a member to a party. Returns True if newly added, False if already present."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO party_members (party_id, telegram_id, telegram_name, joined_at, is_admin) VALUES (?, ?, ?, ?, ?)",
                (party_id, telegram_id, telegram_name, datetime.utcnow().isoformat(), int(is_admin)),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def get_members(party_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM party_members WHERE party_id = ? ORDER BY joined_at",
            (party_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_member(party_id: int, telegram_id: int) -> dict | None:
    """Get a single member record."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM party_members WHERE party_id = ? AND telegram_id = ?",
            (party_id, telegram_id),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def remove_member(party_id: int, telegram_id: int) -> None:
    """Remove a member and all their fillings from a party."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM fillings WHERE party_id = ? AND added_by_id = ?",
            (party_id, telegram_id),
        )
        await db.execute(
            "DELETE FROM party_members WHERE party_id = ? AND telegram_id = ?",
            (party_id, telegram_id),
        )
        await db.commit()


async def is_user_admin(party_id: int, telegram_id: int) -> bool:
    """Check if a user is an admin of a party."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT is_admin FROM party_members WHERE party_id = ? AND telegram_id = ?",
            (party_id, telegram_id),
        )
        row = await cursor.fetchone()
        return bool(row and row[0])


async def promote_admin(party_id: int, telegram_id: int) -> None:
    """Promote a member to admin."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE party_members SET is_admin = 1 WHERE party_id = ? AND telegram_id = ?",
            (party_id, telegram_id),
        )
        await db.commit()


async def demote_admin(party_id: int, telegram_id: int) -> None:
    """Remove admin role from a member."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE party_members SET is_admin = 0 WHERE party_id = ? AND telegram_id = ?",
            (party_id, telegram_id),
        )
        await db.commit()


async def delete_party(party_id: int) -> None:
    """Delete a party and all its members and fillings."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM fillings WHERE party_id = ?", (party_id,))
        await db.execute("DELETE FROM party_members WHERE party_id = ?", (party_id,))
        await db.execute("DELETE FROM parties WHERE id = ?", (party_id,))
        await db.commit()


async def search_members(party_id: int, query: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM party_members WHERE party_id = ? AND telegram_name LIKE ? ORDER BY telegram_name",
            (party_id, f"%{query}%"),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# --------------- Fillings CRUD ---------------

async def add_filling(party_id: int, name: str, added_by_id: int, added_by_name: str) -> int:
    """Add a filling and return its id."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO fillings (party_id, name, added_by_id, added_by_name, created_at) VALUES (?, ?, ?, ?, ?)",
            (party_id, name, added_by_id, added_by_name, datetime.utcnow().isoformat()),
        )
        await db.commit()
        return cursor.lastrowid


async def get_fillings(party_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM fillings WHERE party_id = ? ORDER BY created_at",
            (party_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_user_fillings(party_id: int, telegram_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM fillings WHERE party_id = ? AND added_by_id = ? ORDER BY created_at",
            (party_id, telegram_id),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_filling_by_id(filling_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM fillings WHERE id = ?", (filling_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def find_duplicate_filling(party_id: int, name: str) -> dict | None:
    """Check if a filling with the same name (case-insensitive) exists in the party."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM fillings WHERE party_id = ? AND LOWER(name) = LOWER(?)",
            (party_id, name),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def rename_filling(filling_id: int, new_name: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE fillings SET name = ? WHERE id = ?",
            (new_name, filling_id),
        )
        await db.commit()


async def delete_filling(filling_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM fillings WHERE id = ?", (filling_id,))
        await db.commit()
