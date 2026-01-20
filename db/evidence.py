import asyncpg
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class Evidence:
    """
    Represents evidence that can be analyzed.
    Data is shared across all guilds (no guild_id).
    """
    id: Optional[int] = None
    analysis_number: str = ""
    hint: str = ""
    gm_notes: str = ""

    async def upsert(self, conn: asyncpg.Connection):
        """
        Insert or update this Evidence entry.
        The analysis_number must be unique.
        """
        query = """
        INSERT INTO Evidence (analysis_number, hint, gm_notes)
        VALUES ($1, $2, $3)
        ON CONFLICT (analysis_number) DO UPDATE
        SET hint = EXCLUDED.hint,
            gm_notes = EXCLUDED.gm_notes;
        """
        await conn.execute(query, self.analysis_number, self.hint, self.gm_notes)

    @classmethod
    async def fetch_by_analysis_number(cls, conn: asyncpg.Connection, analysis_number: str) -> Optional["Evidence"]:
        """
        Fetch Evidence by its analysis_number.
        """
        row = await conn.fetchrow("""
            SELECT id, analysis_number, hint, gm_notes
            FROM Evidence
            WHERE analysis_number = $1;
        """, analysis_number)
        if not row:
            return None
        return cls(**dict(row))

    @classmethod
    async def fetch_all(cls, conn: asyncpg.Connection) -> list["Evidence"]:
        """
        Fetch all Evidence entries.
        """
        rows = await conn.fetch("""
            SELECT id, analysis_number, hint, gm_notes
            FROM Evidence
            ORDER BY analysis_number;
        """)
        return [cls(**dict(row)) for row in rows]

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection):
        """
        Delete all Evidence entries.
        """
        result = await conn.execute("DELETE FROM Evidence;")
        logger.warning(f"All Evidence entries deleted. Result: {result}")
