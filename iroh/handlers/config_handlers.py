"""
Configuration handlers for wargame config management.
"""
import asyncpg
from typing import Tuple, Optional, Dict
from db import WargameConfig
import logging

logger = logging.getLogger(__name__)


async def fetch_wargame_config(
    conn: asyncpg.Connection,
    guild_id: int
) -> Tuple[bool, str, Optional[WargameConfig]]:
    """
    Fetch wargame config for editing.

    Args:
        conn: Database connection
        guild_id: Guild ID

    Returns:
        (success, message, config)
    """
    config = await WargameConfig.fetch(conn, guild_id)

    if not config:
        # Create default config if none exists
        config = WargameConfig(guild_id=guild_id)
        await config.upsert(conn)
        logger.info(f"Created default WargameConfig for guild {guild_id}")

    return True, "Config fetched successfully.", config
