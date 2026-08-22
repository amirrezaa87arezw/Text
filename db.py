# -*- coding: utf-8 -*-
import aiosqlite
import config

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id INTEGER PRIMARY KEY,
    profile_summary TEXT,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


async def init_db():
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(CREATE_TABLE_SQL)
        await db.commit()


async def save_profile(user_id: int, profile_summary: str):
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO user_profiles (user_id, profile_summary, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                profile_summary = excluded.profile_summary,
                updated_at = CURRENT_TIMESTAMP
            """,
            (user_id, profile_summary),
        )
        await db.commit()


async def get_profile(user_id: int):
    async with aiosqlite.connect(config.DB_PATH) as db:
        cursor = await db.execute(
            "SELECT profile_summary FROM user_profiles WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None
