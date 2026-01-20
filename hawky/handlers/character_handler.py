import asyncpg
import discord
from typing import Optional, Tuple
from db import Character
import logging

logger = logging.getLogger(__name__)

# Discord allows 50 channels per category, but we use 45 to leave headroom
CATEGORY_CHANNEL_LIMIT = 45


async def get_or_create_available_category(
    guild: discord.Guild,
    base_category_id: int
) -> Optional[discord.CategoryChannel]:
    """
    Get the base category if it has room, or find/create an overflow category.
    Overflow categories use "-2", "-3", etc. suffixes.

    Args:
        guild: Discord guild object
        base_category_id: ID of the base category to start with

    Returns:
        A category with room for new channels, or None if no category can be found/created.
    """
    base_category = discord.utils.get(guild.categories, id=base_category_id)
    if base_category is None:
        return None

    # Check if base category has room
    if len(base_category.channels) < CATEGORY_CHANNEL_LIMIT:
        return base_category

    # Look for existing overflow categories
    base_name = base_category.name
    suffix = 2
    while True:
        overflow_name = f"{base_name}-{suffix}"
        overflow_cat = discord.utils.get(guild.categories, name=overflow_name)

        if overflow_cat is None:
            # Create new overflow category
            overflow_cat = await guild.create_category(overflow_name)
            logger.info(f"Created overflow category '{overflow_name}'")
            return overflow_cat

        if len(overflow_cat.channels) < CATEGORY_CHANNEL_LIMIT:
            return overflow_cat

        suffix += 1
        if suffix > 10:  # Safety limit
            logger.error(f"Reached overflow category limit (10) for base category '{base_name}'")
            return None


async def sort_category_channels(category: discord.CategoryChannel) -> None:
    """
    Sort all text channels in a category alphabetically.

    Args:
        category: The Discord category to sort channels in
    """
    # Get all text channels sorted alphabetically
    text_channels = sorted(
        [c for c in category.channels if isinstance(c, discord.TextChannel)],
        key=lambda c: c.name.lower()
    )

    # Move each channel to its correct position
    for i, ch in enumerate(text_channels):
        try:
            await ch.edit(position=i)
        except discord.HTTPException:
            pass  # Best effort


async def create_character_with_channel(
    conn: asyncpg.Connection,
    guild: discord.Guild,
    identifier: str,
    name: str,
    letter_limit: Optional[int],
    category_id: int,
    sort_channels: bool = True
) -> Tuple[bool, str, Optional[Character]]:
    """
    Create a character with its Discord channel.

    Args:
        conn: Database connection
        guild: Discord guild object
        identifier: Unique identifier for the character (also used as channel name)
        name: Display name for the character
        letter_limit: Daily letter limit (None = unlimited)
        category_id: ID of the Discord category to create the channel in
        sort_channels: Whether to sort channels alphabetically after creation (default True)

    Returns:
        Tuple of (success, message, character or None)
    """
    # Check if character already exists in the database
    existing_character = await Character.fetch_by_identifier(conn, identifier, guild.id)
    if existing_character is not None:
        return (False, f"Character with identifier '{identifier}' already exists", None)

    # Get the base category
    base_category = discord.utils.get(guild.categories, id=category_id)
    if base_category is None:
        return (False, f"Category with ID {category_id} not found", None)

    # Check if a channel with this identifier already exists in the base category
    existing_channel = discord.utils.get(base_category.channels, name=identifier)

    if existing_channel is not None:
        # Use the existing channel
        channel = existing_channel
        category = base_category
        logger.info(f"Using existing channel '{identifier}' for character")
    else:
        # Get an available category (base or overflow)
        category = await get_or_create_available_category(guild, category_id)
        if category is None:
            return (False, "All categories have reached the channel limit", None)

        # Get existing text channels in the target category
        existing_text_channels = [c for c in category.channels if isinstance(c, discord.TextChannel)]

        # Find where the new channel should go alphabetically
        insert_index = len(existing_text_channels)  # Default to end
        for i, ch in enumerate(existing_text_channels):
            if identifier.lower() < ch.name.lower():
                insert_index = i
                break

        logger.info(f"Got channel list: {existing_text_channels}")

        # Calculate actual position based on the channel that should come after us
        if insert_index < len(existing_text_channels):
            # Use the position of the channel that should come after us
            position = existing_text_channels[insert_index].position
        elif existing_text_channels:
            # Append after the last channel
            position = existing_text_channels[-1].position + 1
        else:
            # First channel in category
            position = 0

        # Create the channel at the correct position
        channel = await guild.create_text_channel(
            identifier,
            category=category,
            position=position
        )

        logger.info(f"Created channel '{identifier}' in category '{category.name}' at position {position}")

    # Create the character object
    character = Character(
        identifier=identifier,
        name=name,
        channel_id=channel.id,
        letter_limit=letter_limit,
        guild_id=guild.id
    )

    # Write character to the database
    await character.upsert(conn)

    # Fetch the character back to get the database-assigned ID
    character = await Character.fetch_by_identifier(conn, identifier, guild.id)

    logger.info(f"Created character with identifier: {identifier}")
    return (True, f"Created character '{identifier}'", character)
