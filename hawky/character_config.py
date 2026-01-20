import asyncio
import asyncpg
import discord
import yaml
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass
from db import Character, Alias, ServerConfig
from handlers import create_character_with_channel, sort_category_channels
import logging

logger = logging.getLogger(__name__)


@dataclass
class ImportStats:
    """Statistics from a character config import."""
    characters_created: int = 0
    characters_skipped: int = 0
    characters_failed: int = 0
    channels_created: int = 0
    aliases_created: int = 0
    aliases_skipped: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class CharacterConfigManager:
    """Manages character configuration import from YAML files."""

    @staticmethod
    def _validate_config(config: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate the YAML config structure.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(config, dict):
            return False, "Config must be a YAML dictionary"

        characters = config.get('characters', [])
        if not isinstance(characters, list):
            return False, "'characters' must be a list"

        for i, char in enumerate(characters):
            if not isinstance(char, dict):
                return False, f"Character at index {i} must be a dictionary"

            if 'identifier' not in char:
                return False, f"Character at index {i} is missing 'identifier'"

            if not isinstance(char['identifier'], str):
                return False, f"Character at index {i}: 'identifier' must be a string"

            # name is optional, defaults to identifier
            if 'name' in char and not isinstance(char['name'], str):
                return False, f"Character at index {i}: 'name' must be a string"

            letter_limit = char.get('letter_limit')
            if letter_limit is not None and not isinstance(letter_limit, int):
                return False, f"Character at index {i}: 'letter_limit' must be an integer or null"

            aliases = char.get('aliases', [])
            if not isinstance(aliases, list):
                return False, f"Character at index {i}: 'aliases' must be a list"

            for j, alias in enumerate(aliases):
                if not isinstance(alias, str):
                    return False, f"Character at index {i}, alias at index {j}: must be a string"

        standalone_aliases = config.get('standalone_aliases', [])
        if not isinstance(standalone_aliases, list):
            return False, "'standalone_aliases' must be a list"

        for i, alias_entry in enumerate(standalone_aliases):
            if not isinstance(alias_entry, dict):
                return False, f"Standalone alias at index {i} must be a dictionary"

            if 'character_identifier' not in alias_entry:
                return False, f"Standalone alias at index {i} is missing 'character_identifier'"

            if 'alias' not in alias_entry:
                return False, f"Standalone alias at index {i} is missing 'alias'"

        return True, ""

    @staticmethod
    async def _create_alias(
        conn: asyncpg.Connection,
        character: Character,
        alias_str: str,
        guild_id: int,
        stats: ImportStats
    ) -> None:
        """
        Create an alias for a character if it doesn't already exist.

        Args:
            conn: Database connection
            character: The character to create an alias for
            alias_str: The alias string
            guild_id: Discord guild ID
            stats: ImportStats object to update
        """
        # Check if alias already exists as a character identifier
        existing_char = await Character.fetch_by_identifier(conn, alias_str, guild_id)
        if existing_char is not None:
            stats.aliases_skipped += 1
            stats.errors.append(f"Alias '{alias_str}' conflicts with existing character identifier")
            return

        # Check if alias already exists
        if await Alias.exists(conn, alias_str, guild_id):
            stats.aliases_skipped += 1
            return

        # Create the alias
        new_alias = Alias(
            character_id=character.id,
            alias=alias_str,
            guild_id=guild_id
        )
        await new_alias.insert(conn)
        stats.aliases_created += 1
        logger.info(f"Created alias '{alias_str}' for character '{character.identifier}'")

    @staticmethod
    async def import_config(
        conn: asyncpg.Connection,
        guild_id: int,
        config_yaml: str,
        guild: discord.Guild
    ) -> Tuple[bool, str, ImportStats]:
        """
        Import characters and aliases from YAML configuration.

        Args:
            conn: Database connection
            guild_id: Discord guild ID
            config_yaml: YAML configuration string
            guild: Discord guild object for creating channels

        Returns:
            Tuple of (success, message, stats)
        """
        stats = ImportStats()

        # Parse YAML
        try:
            config = yaml.safe_load(config_yaml)
        except yaml.YAMLError as e:
            return False, f"Invalid YAML: {e}", stats

        # Validate structure
        is_valid, error = CharacterConfigManager._validate_config(config)
        if not is_valid:
            return False, f"Config validation failed: {error}", stats

        # Get server config for default_limit and category_id
        server_config = await ServerConfig.fetch(conn, guild_id)
        if server_config is None:
            return False, "Server configuration not found. Please run /config-server first.", stats

        if server_config.category_id is None:
            return False, "Category ID not configured in server settings.", stats

        # Get the category to check for existing channels
        category = discord.utils.get(guild.categories, id=server_config.category_id)
        if category is None:
            return False, "Configured category not found in guild.", stats

        # Process characters - sort alphabetically by identifier for consistent ordering
        characters = config.get('characters', [])
        characters = sorted(characters, key=lambda c: c.get('identifier', '').lower())
        created_characters: Dict[str, Character] = {}

        for char_config in characters:
            identifier = char_config['identifier']
            name = char_config.get('name', identifier)  # Default to identifier if not provided

            # Determine letter_limit: use config value, or server default if not specified
            # A value of `null` in YAML means unlimited (None)
            if 'letter_limit' in char_config:
                letter_limit = char_config['letter_limit']  # Could be None for unlimited
            else:
                letter_limit = server_config.default_limit

            # Check if character already exists
            existing = await Character.fetch_by_identifier(conn, identifier, guild_id)
            if existing is not None:
                stats.characters_skipped += 1
                created_characters[identifier] = existing
                logger.info(f"Skipped existing character '{identifier}'")

                # Still process inline aliases for existing characters
                inline_aliases = char_config.get('aliases', [])
                for alias_str in inline_aliases:
                    await CharacterConfigManager._create_alias(
                        conn, existing, alias_str, guild_id, stats
                    )
                continue

            # Track if we're creating a new channel
            existing_channel = discord.utils.get(category.channels, name=identifier)

            # Create character with channel using the shared handler
            # Skip sorting during bulk import - we'll sort once at the end
            success, message, character = await create_character_with_channel(
                conn=conn,
                guild=guild,
                identifier=identifier,
                name=name,
                letter_limit=letter_limit,
                category_id=server_config.category_id,
                sort_channels=False
            )

            if success and character:
                stats.characters_created += 1
                if existing_channel is None:
                    stats.channels_created += 1
                created_characters[identifier] = character

                # Process inline aliases
                inline_aliases = char_config.get('aliases', [])
                for alias_str in inline_aliases:
                    await CharacterConfigManager._create_alias(
                        conn, character, alias_str, guild_id, stats
                    )
            else:
                stats.characters_failed += 1
                stats.errors.append(f"Failed to create character '{identifier}': {message}")

            # Sleep to avoid rate limiting
            await asyncio.sleep(0.5)

        # Process standalone aliases
        standalone_aliases = config.get('standalone_aliases', [])
        for alias_entry in standalone_aliases:
            char_identifier = alias_entry['character_identifier']
            alias_str = alias_entry['alias']

            # Get the character (may have been created above or already existed)
            character = created_characters.get(char_identifier)
            if character is None:
                # Try to fetch from database
                character = await Character.fetch_by_identifier(conn, char_identifier, guild_id)

            if character is None:
                stats.aliases_skipped += 1
                stats.errors.append(f"Standalone alias '{alias_str}': character '{char_identifier}' not found")
                continue

            await CharacterConfigManager._create_alias(
                conn, character, alias_str, guild_id, stats
            )

        # Sort channels alphabetically after all characters are created
        #if stats.channels_created > 0:
        #    await sort_category_channels(category)

        # Build summary message
        summary_parts = []
        if stats.characters_created > 0:
            summary_parts.append(f"{stats.characters_created} character(s) created")
        if stats.characters_skipped > 0:
            summary_parts.append(f"{stats.characters_skipped} character(s) skipped (already exist)")
        if stats.characters_failed > 0:
            summary_parts.append(f"{stats.characters_failed} character(s) failed")
        if stats.channels_created > 0:
            summary_parts.append(f"{stats.channels_created} channel(s) created")
        if stats.aliases_created > 0:
            summary_parts.append(f"{stats.aliases_created} alias(es) created")
        if stats.aliases_skipped > 0:
            summary_parts.append(f"{stats.aliases_skipped} alias(es) skipped")

        summary = ", ".join(summary_parts) if summary_parts else "No changes made"

        if stats.errors:
            summary += f"\n\nWarnings/Errors:\n" + "\n".join(f"- {e}" for e in stats.errors[:10])
            if len(stats.errors) > 10:
                summary += f"\n... and {len(stats.errors) - 10} more"

        return True, summary, stats
