import asyncpg
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class SentLetter:
    id: Optional[int] = None
    message_id: int = 0
    channel_id: int = 0
    sender_identifier: str = ""
    recipient_identifier: str = ""
    original_message_channel_id: int = 0
    original_message_id: int = 0
    has_response: bool = False
    guild_id: int = 0
    sent_time: Optional[datetime] = None

    async def insert(self, conn: asyncpg.Connection):
        """
        Insert a new SentLetter entry into the database.
        """
        query = """
        INSERT INTO SentLetter (
            message_id, channel_id, sender_identifier, recipient_identifier,
            original_message_channel_id, original_message_id, has_response,
            guild_id, sent_time
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id;
        """
        row = await conn.fetchrow(
            query,
            self.message_id,
            self.channel_id,
            self.sender_identifier,
            self.recipient_identifier,
            self.original_message_channel_id,
            self.original_message_id,
            self.has_response,
            self.guild_id,
            self.sent_time
        )
        self.id = row['id']

    @classmethod
    async def fetch_by_message_id(cls, conn: asyncpg.Connection, message_id: int, guild_id: int) -> Optional["SentLetter"]:
        """
        Fetch a SentLetter by its message_id and guild_id.
        """
        row = await conn.fetchrow("""
            SELECT id, message_id, channel_id, sender_identifier, recipient_identifier,
                   original_message_channel_id, original_message_id, has_response,
                   guild_id, sent_time
            FROM SentLetter
            WHERE message_id = $1 AND guild_id = $2;
        """, message_id, guild_id)
        return cls(**row) if row else None

    async def mark_responded(self, conn: asyncpg.Connection):
        """
        Mark this letter as having been responded to.
        """
        await conn.execute("""
            UPDATE SentLetter
            SET has_response = TRUE
            WHERE id = $1;
        """, self.id)
        self.has_response = True

    @classmethod
    async def print_all(cls, conn: asyncpg.Connection):
        """
        Fetch and print all SentLetter entries.
        """
        rows = await conn.fetch("""
            SELECT id, message_id, channel_id, sender_identifier, recipient_identifier,
                   original_message_channel_id, original_message_id, has_response,
                   guild_id, sent_time
            FROM SentLetter
            ORDER BY sent_time DESC;
        """)

        if not rows:
            logger.info("📭 No entries found in SentLetter table.")
            return

        logger.info("📜 SentLetter entries:\n")
        for row in rows:
            logger.info(
                f"✉️ ID: {row['id']}\n"
                f"   • Message ID: {row['message_id']}\n"
                f"   • Channel ID: {row['channel_id']}\n"
                f"   • Sender: {row['sender_identifier']}\n"
                f"   • Recipient: {row['recipient_identifier']}\n"
                f"   • Original Message Channel ID: {row['original_message_channel_id']}\n"
                f"   • Original Message ID: {row['original_message_id']}\n"
                f"   • Has Response: {row['has_response']}\n"
                f"   • Guild ID: {row['guild_id']}\n"
                f"   • Sent Time: {row['sent_time']}\n"
            )

    @classmethod
    async def delete_all(cls, conn: asyncpg.Connection):
        """
        Delete all entries from the SentLetter table.
        """
        result = await conn.execute("DELETE FROM SentLetter;")
        logger.warning(f"⚠️ All entries deleted from SentLetter table. Result: {result}")
