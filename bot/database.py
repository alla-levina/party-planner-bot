"""Database layer – PostgreSQL via asyncpg."""

import asyncpg
from datetime import datetime, timezone

# Connection pool (initialised in init_db)
_pool: asyncpg.Pool | None = None


async def init_db(database_url: str) -> None:
    """Create the connection pool and tables."""
    global _pool
    _pool = await asyncpg.create_pool(database_url, min_size=1, max_size=5)

    async with _pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS parties (
                id          SERIAL  PRIMARY KEY,
                name        TEXT    NOT NULL,
                code        TEXT    NOT NULL UNIQUE,
                creator_id  BIGINT  NOT NULL,
                created_at  TEXT    NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS fillings (
                id            SERIAL  PRIMARY KEY,
                party_id      INTEGER NOT NULL REFERENCES parties(id),
                name          TEXT    NOT NULL,
                added_by_id   BIGINT  NOT NULL,
                added_by_name TEXT    NOT NULL,
                created_at    TEXT    NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS party_members (
                id             SERIAL  PRIMARY KEY,
                party_id       INTEGER NOT NULL REFERENCES parties(id),
                telegram_id    BIGINT  NOT NULL,
                telegram_name  TEXT    NOT NULL,
                joined_at      TEXT    NOT NULL,
                is_admin       BOOLEAN NOT NULL DEFAULT FALSE,
                UNIQUE(party_id, telegram_id)
            )
            """
        )

        # Migration: add party info columns if missing
        for col in ("info_datetime", "info_address", "info_map_link", "info_description"):
            await conn.execute(f"""
                DO $$ BEGIN
                    ALTER TABLE parties ADD COLUMN {col} TEXT;
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$;
            """)


async def close_db() -> None:
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def _record_to_dict(record: asyncpg.Record | None) -> dict | None:
    """Convert an asyncpg Record to a plain dict."""
    return dict(record) if record else None


# --------------- Party CRUD ---------------

async def has_party_with_name(creator_id: int, name: str) -> bool:
    """Check if a creator already owns an active party with this name (case-insensitive)."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM parties WHERE creator_id = $1 AND LOWER(name) = LOWER($2) LIMIT 1",
            creator_id, name,
        )
        return row is not None


async def create_party(name: str, code: str, creator_id: int) -> int:
    """Create a party and return its id."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO parties (name, code, creator_id, created_at) VALUES ($1, $2, $3, $4) RETURNING id",
            name, code, creator_id, datetime.now(timezone.utc).isoformat(),
        )
        return row["id"]


async def get_party_by_code(code: str) -> dict | None:
    """Look up a party by its unique invite code."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM parties WHERE code = $1", code)
        return _record_to_dict(row)


async def get_party_by_id(party_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM parties WHERE id = $1", party_id)
        return _record_to_dict(row)


async def get_parties_for_user(telegram_id: int) -> list[dict]:
    """Return all parties a user belongs to, including the creator's display name."""
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.*, creator_pm.telegram_name AS creator_name
            FROM parties p
            JOIN party_members pm ON p.id = pm.party_id
            LEFT JOIN party_members creator_pm
                ON p.id = creator_pm.party_id AND p.creator_id = creator_pm.telegram_id
            WHERE pm.telegram_id = $1
            ORDER BY p.created_at DESC
            """,
            telegram_id,
        )
        return [dict(r) for r in rows]


# --------------- Party info ---------------

INFO_FIELDS = ("info_datetime", "info_address", "info_map_link", "info_description")


async def get_party_info(party_id: int) -> dict | None:
    """Return the info fields for a party."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT info_datetime, info_address, info_map_link, info_description FROM parties WHERE id = $1",
            party_id,
        )
        return dict(row) if row else None


async def update_party_info(party_id: int, field: str, value: str | None) -> None:
    """Update a single info field on a party. field must be one of INFO_FIELDS."""
    if field not in INFO_FIELDS:
        raise ValueError(f"Invalid info field: {field}")
    async with _pool.acquire() as conn:
        await conn.execute(
            f"UPDATE parties SET {field} = $1 WHERE id = $2",
            value, party_id,
        )


# --------------- Members CRUD ---------------

async def add_member(party_id: int, telegram_id: int, telegram_name: str, is_admin: bool = False) -> bool:
    """Add a member to a party. Returns True if newly added, False if already present.

    If the member already exists, their display name is refreshed.
    """
    async with _pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO party_members (party_id, telegram_id, telegram_name, joined_at, is_admin) VALUES ($1, $2, $3, $4, $5)",
                party_id, telegram_id, telegram_name, datetime.now(timezone.utc).isoformat(), is_admin,
            )
            return True
        except asyncpg.UniqueViolationError:
            # User already in party — refresh their display name
            await conn.execute(
                "UPDATE party_members SET telegram_name = $1 WHERE party_id = $2 AND telegram_id = $3",
                telegram_name, party_id, telegram_id,
            )
            return False


async def update_member_name(party_id: int, telegram_id: int, telegram_name: str) -> None:
    """Update a member's display name (keeps it current when usernames change)."""
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE party_members SET telegram_name = $1 WHERE party_id = $2 AND telegram_id = $3",
            telegram_name, party_id, telegram_id,
        )


async def get_members(party_id: int) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM party_members WHERE party_id = $1 ORDER BY joined_at",
            party_id,
        )
        return [dict(r) for r in rows]


async def get_member(party_id: int, telegram_id: int) -> dict | None:
    """Get a single member record."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM party_members WHERE party_id = $1 AND telegram_id = $2",
            party_id, telegram_id,
        )
        return _record_to_dict(row)


async def remove_member(party_id: int, telegram_id: int) -> None:
    """Remove a member and all their fillings from a party."""
    async with _pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM fillings WHERE party_id = $1 AND added_by_id = $2",
                party_id, telegram_id,
            )
            await conn.execute(
                "DELETE FROM party_members WHERE party_id = $1 AND telegram_id = $2",
                party_id, telegram_id,
            )


async def is_user_admin(party_id: int, telegram_id: int) -> bool:
    """Check if a user is an admin of a party."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT is_admin FROM party_members WHERE party_id = $1 AND telegram_id = $2",
            party_id, telegram_id,
        )
        return bool(row and row["is_admin"])


async def promote_admin(party_id: int, telegram_id: int) -> None:
    """Promote a member to admin."""
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE party_members SET is_admin = TRUE WHERE party_id = $1 AND telegram_id = $2",
            party_id, telegram_id,
        )


async def demote_admin(party_id: int, telegram_id: int) -> None:
    """Remove admin role from a member."""
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE party_members SET is_admin = FALSE WHERE party_id = $1 AND telegram_id = $2",
            party_id, telegram_id,
        )


async def delete_party(party_id: int) -> None:
    """Delete a party and all its members and fillings."""
    async with _pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM fillings WHERE party_id = $1", party_id)
            await conn.execute("DELETE FROM party_members WHERE party_id = $1", party_id)
            await conn.execute("DELETE FROM parties WHERE id = $1", party_id)


async def search_members(party_id: int, query: str) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM party_members WHERE party_id = $1 AND telegram_name ILIKE $2 ORDER BY telegram_name",
            party_id, f"%{query}%",
        )
        return [dict(r) for r in rows]


# --------------- Fillings CRUD ---------------

async def add_filling(party_id: int, name: str, added_by_id: int, added_by_name: str) -> int:
    """Add a filling and return its id."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO fillings (party_id, name, added_by_id, added_by_name, created_at) VALUES ($1, $2, $3, $4, $5) RETURNING id",
            party_id, name, added_by_id, added_by_name, datetime.now(timezone.utc).isoformat(),
        )
        return row["id"]


async def get_fillings(party_id: int) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM fillings WHERE party_id = $1 ORDER BY created_at",
            party_id,
        )
        return [dict(r) for r in rows]


async def get_user_fillings(party_id: int, telegram_id: int) -> list[dict]:
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM fillings WHERE party_id = $1 AND added_by_id = $2 ORDER BY created_at",
            party_id, telegram_id,
        )
        return [dict(r) for r in rows]


async def get_filling_by_id(filling_id: int) -> dict | None:
    async with _pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM fillings WHERE id = $1", filling_id)
        return _record_to_dict(row)


async def find_duplicate_filling(party_id: int, name: str) -> dict | None:
    """Check if a filling with the same name (case-insensitive) exists in the party."""
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM fillings WHERE party_id = $1 AND LOWER(name) = LOWER($2)",
            party_id, name,
        )
        return _record_to_dict(row)


async def rename_filling(filling_id: int, new_name: str) -> None:
    async with _pool.acquire() as conn:
        await conn.execute(
            "UPDATE fillings SET name = $1 WHERE id = $2",
            new_name, filling_id,
        )


async def delete_filling(filling_id: int) -> None:
    async with _pool.acquire() as conn:
        await conn.execute("DELETE FROM fillings WHERE id = $1", filling_id)
