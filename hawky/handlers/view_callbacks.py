import discord
from helpers import emotive_message
import asyncpg
from db import Character
from typing import Optional


async def assign_character_callback(interaction: discord.Interaction,
                                    new_identifier: str,
                                    old_character: Optional[Character],
                                    user_id: int):
    # When the response has been processed check if the value is the same as the previous value
    # If so, we are done
    # If not, check whether user had a character before
    if new_identifier != old_character:
        conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
        member = await interaction.guild.fetch_member(user_id)
        if old_character is not None:
            # If so, remove them from the associated channel
            old_channel = await interaction.guild.fetch_channel(old_character.channel_id)
            await old_channel.set_permissions(member, overwrite=None)

            # Update the old character to not have a user ID
            old_character.user_id = None
            await old_character.upsert(conn)

        if new_identifier != "None":
            # Get the new character
            new_character = await Character.fetch_by_identifier(conn,
                                                                new_identifier,
                                                                interaction.guild_id)

            if new_character is None:
                await conn.close()
                await interaction.response.send_message(
                    emotive_message(f"Character '{new_identifier}' not found"),
                    ephemeral=True)
                return

            # Add them to the new channel
            overwrite = discord.PermissionOverwrite()
            overwrite.send_messages = True
            overwrite.read_messages = True
            new_channel = await interaction.guild.fetch_channel(new_character.channel_id)
            await new_channel.set_permissions(member, overwrite=overwrite)

            # Assign to this character in the database
            # Add user to character
            new_character.user_id = user_id

            # Write to Database
            await new_character.upsert(conn)
        await conn.close()


    # Send confirmation
    if new_identifier == "None":
        await interaction.response.send_message(
            content=f"Removed character assignment",
            ephemeral=True)
    else:
        await interaction.response.send_message(
            content=f"Assigned character with identifier: {new_identifier}",
            ephemeral=True)


async def config_character_callback(interaction: discord.Interaction,
                                    character: Character,
                                    limit_str: Optional[str],
                                    count_str: Optional[str],
                                    name: str):
    limit = None
    # Parse limit as an int
    if limit_str is not None and len(limit_str) > 0:
        try:
            limit = int(limit_str)
        except ValueError:
            await interaction.response.send_message(
                emotive_message('Invalid Limit. Please enter a non-negative number.'),
                ephemeral=True)
            return

    count = None
    if count_str is not None and len(count_str) > 0:
        try:
            count = int(count_str)
        except ValueError:
            await interaction.response.send_message(
                emotive_message('Invalid Letter count. Please enter a non-negative number.'),
                ephemeral=True)
            return

    # Update character
    character.letter_limit = limit
    character.letter_count = count
    character.name = name

    # Verify values
    ok, message = character.verify()

    if not ok:
        await interaction.response.send_message(emotive_message(message), ephemeral=True)
        return

    # Upsert result
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
    await character.upsert(conn)
    await conn.close()
    await interaction.response.send_message(
        emotive_message(f"Character {character.identifier} Updated"), ephemeral=True)
