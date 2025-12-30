import discord
from discord import app_commands
from discord.ext import commands, tasks
from helpers import *
from views import *
import os
import logging
from dotenv import load_dotenv
from db import *
from datetime import datetime, timedelta
from tasks.send_letter import handle_send_letter
from tasks.remind_me import handle_remind_me
from tasks.send_response import handle_send_response
import re

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - Hawky Logging - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')
DB_URL = "postgresql://AVATAR:password@db:5432/AVATAR"

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

# Global connection pool
db_pool = None


# Task Handler
@tasks.loop(seconds=60)
async def process_hawky_tasks():
    """Process pending tasks from the HawkyTask table."""
    async with db_pool.acquire() as conn:
        try:
            # Get the next task that's due
            task = await HawkyTask.pop_next_task(conn, datetime.now())

            while task is not None:
                # Handle different task types
                if task.task == "send_letter":
                    try:
                        await handle_send_letter(client, conn, task)
                        logger.info(f"Successfully sent letter from {task.sender_identifier} to {task.recipient_identifier}")
                    except Exception as e:
                        logger.error(f"Error sending letter (task {task.id}): {e}", exc_info=True)
                elif task.task == "reset_counts":
                    try:
                        await handle_reset_counts(conn, task)
                        logger.info(f"Successfully reset letter counts for guild {task.guild_id}")
                    except Exception as e:
                        logger.error(f"Error resetting counts (task {task.id}): {e}", exc_info=True)
                elif task.task == "remind_me":
                    try:
                        await handle_remind_me(client, conn, task)
                        logger.info(f"Successfully sent reminder to user {task.recipient_identifier}")
                    except Exception as e:
                        logger.error(f"Error sending reminder (task {task.id}): {e}", exc_info=True)
                elif task.task == "send_response":
                    try:
                        await handle_send_response(client, conn, task)
                        logger.info(f"Successfully sent response from {task.sender_identifier} to {task.recipient_identifier}")
                    except Exception as e:
                        logger.error(f"Error sending response (task {task.id}): {e}", exc_info=True)
                else:
                    logger.warning(f"Unknown task type: {task.task}")

                # Get the next task
                task = await HawkyTask.pop_next_task(conn, datetime.now())

        except Exception as e:
            logger.error(f"Error processing tasks: {e}", exc_info=True)

async def handle_reset_counts(conn: asyncpg.Connection, task: HawkyTask):
    """
    Handle a reset_counts task by resetting letter counts for a guild
    and scheduling the next reset based on the server's configured reset_time.
    """
    # Reset letter counts for the guild
    await Character.reset_letter_counts(conn, task.guild_id)

    # Get the server config to find the reset time
    server_config = await ServerConfig.fetch(conn, task.guild_id)

    # Determine the reset time (default to midnight if not configured)
    from datetime import time as time_type
    reset_time = server_config.reset_time if server_config and server_config.reset_time else time_type(0, 0)

    # Calculate next reset occurrence
    now = datetime.now()
    next_reset = datetime.combine(now.date() + timedelta(days=1), reset_time)

    # Schedule the next reset task
    next_task = HawkyTask(
        task="reset_counts",
        guild_id=task.guild_id,
        scheduled_time=next_reset
    )
    await next_task.insert(conn)

    logger.info(f"Scheduled next reset for guild {task.guild_id} at {next_reset}")


# Public Commands
@client.event
async def on_ready():
    global db_pool
    # Initialize the connection pool
    db_pool = await asyncpg.create_pool(
        DB_URL,
        min_size=2,
        max_size=10,
        command_timeout=60
    )
    logger.info("Database connection pool initialized")

    await tree.sync()
    process_hawky_tasks.start()  # Start the task processing loop
    logger.info(f'We have logged in as {client.user}')

@tree.command(
    name="whistle",
    description="Whistle for hawky"
)
async def whistle(interaction: discord.Interaction):
    await interaction.response.send_message(get_emote_text())

@tree.context_menu(
    name="Send as Letter"
)
async def send_letter(interaction: discord.Interaction, message: discord.Message):
    # Get the characters for the sender
    async with db_pool.acquire() as conn:
        sender = Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
        characters = Character.fetch_all(conn, interaction.guild_id)
        server_config = ServerConfig.fetch(conn, interaction.guild_id)
        sender = await sender
        characters = await characters
        server_config = await server_config

    # Check if user is an admin without a character
    is_admin = interaction.user.guild_permissions.manage_guild
    if sender is None and is_admin and server_config and server_config.admin_response_channel_id:
        # Admin without character can send letters if admin response channel is configured
        view = SendLetterView(message, None, characters, send_letter_callback)
        await interaction.response.send_message(emotive_message("Select a character"),
                                                view=view,
                                                ephemeral=True)
    elif sender is None:
        # User has no character and isn't an admin or admin channel not configured
        await interaction.response.send_message(
            emotive_message("You don't have a character assigned!"),
            ephemeral=True)
    elif sender.letter_limit is None or sender.letter_limit - sender.letter_count > 0:
        view = SendLetterView(message, sender, characters, send_letter_callback)
        await interaction.response.send_message(emotive_message("Select a character"),
                                                view=view,
                                                ephemeral=True)
    else:
        await interaction.response.send_message(
            emotive_message("You have no letters remaining!"),
            ephemeral = True)

async def send_letter_callback(interaction: discord.Interaction,
                               message: discord.Message,
                               sender: Character,
                               recipient_identifier: str):
    # Get the characters for the sender and the recipient
    async with db_pool.acquire() as conn:
        guild_id = interaction.guild_id
        recipient = await Character.fetch_by_identifier(conn, recipient_identifier, guild_id)

        # Get the ServerConfig for this server to get the letter delay
        config = ServerConfig.fetch(conn, guild_id)

        # Confirm that the user wants to send a letter to this character
        # Replace the dropdown with the confirmation view
        view = Confirm()
        message_content = f"Are you sure you want to send this message to {recipient.name}?"
        if sender is not None and sender.letter_limit is not None:
            message_content = f"You have {sender.letter_limit - sender.letter_count} letters remaining today. " + message_content
        await interaction.response.edit_message(
            content=emotive_message(message_content),
            view=view)
        await view.wait()
        interaction = view.interaction

        if view.value is None:
            await interaction.response.edit_message(
                content=emotive_message("Send letter timed out"),
                view=None)
            return
        elif not view.value:
            await interaction.response.edit_message(
                content=emotive_message("Canceled send letter"),
                view=None)
            return

        # Schedule Send Message Task
        config = await config
        if config is not None and config.letter_delay is not None:
            scheduled_time = datetime.now() + timedelta(minutes=config.letter_delay)
        else:
            # If there is no letter delay, schedule it to go out with the next tick
            scheduled_time = datetime.now()

        # Use a special identifier for admin letters
        sender_identifier = sender.identifier if sender else f"ADMIN:{interaction.user.id}"

        task = HawkyTask(task = "send_letter",
                         recipient_identifier = recipient_identifier,
                         sender_identifier = sender_identifier,
                         parameter = f"{message.channel.id} {message.id}",
                         scheduled_time = scheduled_time,
                         guild_id = guild_id)

        await task.insert(conn)

        # Update count only if sender is a character
        if sender is not None:
            sender.letter_count += 1
            await sender.upsert(conn)

    # Send confirmation
    logger.info(f"Letter queued from {sender_identifier} to {recipient.identifier} (scheduled: {scheduled_time})")
    await interaction.response.edit_message(
        content=emotive_message(f"Message queued to send to {recipient.name}"), view=None)


@tree.context_menu(
    name="Remind Me"
)
async def remind_me(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.send_modal(RemindMeModal(remind_me_callback, message))


async def remind_me_callback(interaction: discord.Interaction, message: discord.Message, time_str: str):
    """
    Parse the time string and schedule a reminder task.
    Supports formats like: "30 minutes", "8 hours", "3 days"
    """
    # Parse the time string
    pattern = r'(\d+)\s*(minute|minutes|min|hour|hours|hr|day|days|d)'
    match = re.search(pattern, time_str.lower())

    if not match:
        await interaction.response.send_message(
            emotive_message("Invalid time format. Please use format like '30 minutes', '8 hours', or '3 days'."),
            ephemeral=True)
        return

    amount = int(match.group(1))
    unit = match.group(2)

    # Calculate the timedelta based on the unit
    if unit.startswith('min'):
        delta = timedelta(minutes=amount)
    elif unit.startswith('hour') or unit.startswith('hr'):
        delta = timedelta(hours=amount)
    elif unit.startswith('day') or unit == 'd':
        delta = timedelta(days=amount)
    else:
        await interaction.response.send_message(
            emotive_message("Invalid time unit. Please use minutes, hours, or days."),
            ephemeral=True)
        return

    # Calculate scheduled time
    scheduled_time = datetime.now() + delta

    # Create the task
    async with db_pool.acquire() as conn:
        task = HawkyTask(
            task="remind_me",
            recipient_identifier=str(interaction.user.id),
            parameter=f"{message.guild.id} {message.channel.id} {message.id}",
            scheduled_time=scheduled_time,
            guild_id=interaction.guild_id
        )
        await task.insert(conn)

    # Send confirmation
    logger.info(f"Reminder set for user {interaction.user.id} in {time_str} (scheduled: {scheduled_time})")
    await interaction.response.send_message(
        emotive_message(f"Reminder set! I'll remind you about this message in {time_str}."),
        ephemeral=True)

@tree.context_menu(
    name="Send as Response"
)
async def send_response(interaction: discord.Interaction, message: discord.Message):
    """
    Send a response to a letter. Fetches all unreplied letters from the last 8 hours.
    If multiple letters exist, shows a selection dialog.
    """
    # Get the character of the sender
    async with db_pool.acquire() as conn:
        sender = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)

        if sender is None:
            await interaction.response.send_message(
                emotive_message("You don't have a character assigned!"),
                ephemeral=True)
            return

        # Check that the message was sent by the user in their own character channel
        if message.author.id != interaction.user.id:
            await interaction.response.send_message(
                emotive_message("You can only send your own messages as responses!"),
                ephemeral=True)
            return

        if message.channel.id != sender.channel_id:
            await interaction.response.send_message(
                emotive_message("You can only send responses from your character's channel!"),
                ephemeral=True)
            return

        # Find all unresponded letters sent to this character within the last 8 hours
        eight_hours_ago = datetime.now() - timedelta(hours=8)
        sent_letter_rows = await conn.fetch("""
            SELECT id, message_id, channel_id, sender_identifier, recipient_identifier,
                original_message_channel_id, original_message_id, has_response,
                guild_id, sent_time
            FROM SentLetter
            WHERE recipient_identifier = $1 AND guild_id = $2 AND has_response = FALSE
            AND sent_time >= $3
            ORDER BY sent_time DESC;
        """, sender.identifier, interaction.guild_id, eight_hours_ago)

        if not sent_letter_rows:
            await interaction.response.send_message(
                emotive_message("No unreplied letters found for your character in the last 8 hours!"),
                ephemeral=True)
            return

        # Fetch the actual message content for each letter
        letters_with_content = []
        for row in sent_letter_rows:
            try:
                # Fetch the original message that was sent
                channel = await client.fetch_channel(row['channel_id'])
                sent_message = await channel.fetch_message(row['message_id'])

                letters_with_content.append({
                    'id': row['id'],
                    'message_id': row['message_id'],
                    'channel_id': row['channel_id'],
                    'sender_identifier': row['sender_identifier'],
                    'recipient_identifier': row['recipient_identifier'],
                    'original_message_channel_id': row['original_message_channel_id'],
                    'original_message_id': row['original_message_id'],
                    'has_response': row['has_response'],
                    'guild_id': row['guild_id'],
                    'sent_time': row['sent_time'],
                    'content': sent_message.content,
                    'attachments': sent_message.attachments
                })
            except Exception as e:
                logger.error(f"Error fetching message content for letter {row['id']}: {e}")
                # Include the letter anyway but with placeholder content
                letters_with_content.append({
                    'id': row['id'],
                    'message_id': row['message_id'],
                    'channel_id': row['channel_id'],
                    'sender_identifier': row['sender_identifier'],
                    'recipient_identifier': row['recipient_identifier'],
                    'original_message_channel_id': row['original_message_channel_id'],
                    'original_message_id': row['original_message_id'],
                    'has_response': row['has_response'],
                    'guild_id': row['guild_id'],
                    'sent_time': row['sent_time'],
                    'content': '[Content unavailable]',
                    'attachments': []
                })

        # If there's only one letter, proceed directly to confirmation
        if len(letters_with_content) == 1:
            await send_response_confirmation(interaction, message, letters_with_content[0], sender, conn)
        else:
            # Multiple letters - show selection dialog
            view = SelectLetterView(message, letters_with_content, send_response_selection_callback)
            await interaction.response.send_message(
                emotive_message(f"You have {len(letters_with_content)} unreplied letters. Please select which one to respond to:"),
                view=view,
                ephemeral=True)


async def send_response_selection_callback(interaction: discord.Interaction, message: discord.Message, selected_letter: dict):
    """
    Callback after user selects which letter to respond to.
    """
    async with db_pool.acquire() as conn:
        sender = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)

        await send_response_confirmation(interaction, message, selected_letter, sender, conn)


async def send_response_confirmation(interaction: discord.Interaction, message: discord.Message, selected_letter: dict, sender: Character, conn):
    """
    Show confirmation dialog and schedule the response task.
    """
    async with db_pool.acquire() as conn:
        # Get the ServerConfig for this server to get the letter delay
        config = await ServerConfig.fetch(conn, interaction.guild_id)

        # Confirm that the user wants to send this response
        view = Confirm()
        message_content = f"Are you sure you want to send this response?"

        # Check if the interaction has already been responded to (from dropdown)
        # If so, edit the message; otherwise send a new one
        if interaction.response.is_done():
            await interaction.edit_original_response(
                content=emotive_message(message_content),
                view=view)
        else:
            await interaction.response.send_message(
                content=emotive_message(message_content),
                view=view,
                ephemeral=True)

        await view.wait()
        interaction = view.interaction

        if view.value is None:
            await interaction.response.edit_message(
                content=emotive_message("Send response timed out"),
                view=None)
            return
        elif not view.value:
            await interaction.response.edit_message(
                content=emotive_message("Canceled send response"),
                view=None)
            return

        # Schedule Send Response Task
        if config is not None and config.letter_delay is not None:
            scheduled_time = datetime.now() + timedelta(minutes=config.letter_delay)
        else:
            # If there is no letter delay, schedule it to go out with the next tick
            scheduled_time = datetime.now()

        task = HawkyTask(
            task="send_response",
            recipient_identifier=selected_letter['sender_identifier'],
            sender_identifier=sender.identifier,
            parameter=f"{message.channel.id} {message.id}",
            scheduled_time=scheduled_time,
            guild_id=interaction.guild_id
        )

        await task.insert(conn)

        # Mark the original letter as responded to
        sent_letter = SentLetter(**{k: v for k, v in selected_letter.items() if k != 'content' and k != 'attachments'})
        await sent_letter.mark_responded(conn)

    # Send confirmation
    logger.info(f"Response queued from {sender.identifier} to {selected_letter['sender_identifier']} (scheduled: {scheduled_time})")
    await interaction.response.edit_message(
        content=emotive_message(f"Response queued"),
        view=None)


@tree.command(
    name="check-letter-limit",
    description="Check your remaining daily letter allocation"
)
async def check_letter_limit(interaction: discord.Interaction):
    async with db_pool.acquire() as conn:
        character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)

    if character is None:
        await interaction.response.send_message(
            emotive_message("You don't have a character assigned yet"),
            ephemeral=True)
        return

    if character.letter_limit is None:
        await interaction.response.send_message(
            emotive_message("You have unlimited letters"),
            ephemeral=True)
    else:
        remaining_letters = character.letter_limit - character.letter_count
        await interaction.response.send_message(
            emotive_message(f'You have {remaining_letters} letters remaining out of a maximum of {character.letter_limit}'),
            ephemeral=True)

# Admin Commands
@tree.command(
    name="create-character",
    description="Create a new character in the DB and then start a configuration menu for that character"
)
@app_commands.describe(
    identifier="The identifier you want to use for the new character. Will be used as the channel name, must be unique for this server"
)
@app_commands.default_permissions(manage_guild=True)
async def create_character(interaction: discord.Interaction, identifier: str):
    # Get server settings for this guild
    async with db_pool.acquire() as conn:
        server_config = await ServerConfig.fetch(conn, interaction.guild_id)

    # If those don't exist, send error message and abort
    if server_config is None:
        await interaction.response.send_message(
            emotive_message("You need to set the server configuration before you can create a character"),
            ephemeral=True)
        return

    # Use the category ID from server settings to get the actual category object
    category = None
    if server_config.category_id is not None:
        category = discord.utils.get(interaction.guild.categories, id=server_config.category_id)
    else:
        await interaction.response.send_message(
            emotive_message("You need to set character channel in the server configuration before you can create a character"),
            ephemeral=True)
        return

    # Check if the character already exists in the database
    async with db_pool.acquire() as conn:
        character = await Character.fetch_by_identifier(conn, identifier, interaction.guild_id)

    if character is not None:
        await interaction.response.send_message(
            emotive_message(f"A character with the identifier {identifier} already exists in the database, aborting."),
            ephemeral = True
        )
        return
    
    # Check if there's already a channel with this identifier in the specified category
    channel = discord.utils.get(category.channels, name=identifier)

    sent_confirmation = False

    if channel is None:
        # If not, make the channel in alphabetical order
        # Find the correct position based on alphabetical ordering
        category_channels = sorted(category.channels, key=lambda c: c.name.lower())
        position = 0
        for i, ch in enumerate(category_channels):
            if identifier.lower() < ch.name.lower():
                position = ch.position - 1
                break
            position = ch.position

        channel = await interaction.guild.create_text_channel(identifier, category=category, position=position)

    else:
        # If there is, send confirmation checking whether it should connect this character to that channel
        sent_confirmation = True
        view = Confirm()
        await interaction.response.send_message(
            emotive_message(f"A channel called {identifier} already exists in the configured category. Would you like to connect this character to it?"),
            view=view,
            ephemeral = True)
        await view.wait()
        interaction = view.interaction

        if view.value is None:
            # If not confirmed, abort
            await interaction.response.edit_message(
                content=emotive_message("Character Creation Timed Out"),
                view=None)
            return

        elif not view.value:
            # If not confirmed, abort
            await interaction.response.edit_message(
                content=emotive_message("Canceled Create Character"),
                view=None)
            return


    # Create the character object
    character = Character(identifier=identifier,
                          name=identifier,
                          channel_id = channel.id,
                          letter_limit = server_config.default_limit,
                          guild_id = interaction.guild_id)

    # Write character to the database
    async with db_pool.acquire() as conn:
        await character.upsert(conn)

    logger.info(f"Created character with identifier: {identifier}")
    if sent_confirmation:
        await interaction.response.edit_message(
            content=emotive_message(f'Created character with identifier: {identifier}'), view=None)
    else:
        await interaction.response.send_message(
            content=emotive_message(f'Created character with identifier: {identifier}'), ephemeral=True)

@tree.command(
    name="remove-character",
    description="Remove a new character from the DB and its associated channel"
)
@app_commands.describe(
    identifier="The identifier of the character you want to remove"
)
@app_commands.default_permissions(manage_guild=True)
async def remove_character(interaction: discord.Interaction, identifier: str):
    # Get the character from the database
    async with db_pool.acquire() as conn:
        character = await Character.fetch_by_identifier(conn, identifier, interaction.guild_id)

        # If that character doesn't exist, abort
        if character is None:
            await interaction.response.send_message(
                emotive_message(f"There is no character with the identifier {identifier} in the database"),
                ephemeral = True)
            return

        # Show confirmation dialog before deleting
        view = Confirm()
        await interaction.response.send_message(
            emotive_message(f"Are you sure you want to delete the character '{identifier}' and its associated channel? This action cannot be undone."),
            view=view,
            ephemeral=True)
        await view.wait()
        interaction = view.interaction

        if view.value is None:
            await interaction.response.edit_message(
                content=emotive_message("Character deletion timed out"),
                view=None)
            return
        elif not view.value:
            await interaction.response.edit_message(
                content=emotive_message("Canceled character deletion"),
                view=None)
            return

        # Delete the associated channel
        delete_channel = interaction.guild.get_channel(character.channel_id).delete()

        # Delete the character from the database
        delete_database = Character.delete(conn, character.id)

        await delete_channel
        await delete_database

    # Send confirmation
    logger.info(f"Successfully deleted {identifier}")

    await interaction.response.edit_message(
        content=emotive_message(f"Successfully deleted {identifier}"),
        view=None)
    

@tree.command(
    name="config-character",
    description="Configure the specified character, updating its entry in the database"
)
@app_commands.describe(
    identifier="The identifier of the character you want to configure"
)
@app_commands.default_permissions(manage_guild=True)
async def config_character(interaction: discord.Interaction, identifier: str):
    # Get exisitng character entry
    async with db_pool.acquire() as conn:
        character = await Character.fetch_by_identifier(conn, identifier, interaction.guild_id)
    
    # If it doesn't exist, send an error message
    if character is None:
        await interaction.response.send_message(
            emotive_message(f"No character with the identifier {identifier} exists"),
            ephemeral=True)
    else:
        # Otherwise, send the config
        await interaction.response.send_modal(ConfigCharacterModal(character))
    
    
@tree.context_menu(name='Assign Character')
@app_commands.default_permissions(manage_guild=True)
async def assign_character(interaction: discord.Interaction, member: discord.Member):
    async with db_pool.acquire() as conn:
        # Get the user's previous character
        old_character = Character.fetch_by_user(conn, member.id, interaction.guild_id)
        
        # Send menu with dropdown to select un-selected characters
        unowned_characters = Character.fetch_unowned(conn, interaction.guild_id)

        old_character = await old_character
        unowned_characters = await unowned_characters

    view = AssignCharacterView(old_character, unowned_characters, member.id)
    await interaction.response.send_message("Select a character", view=view, ephemeral=True)    

@tree.context_menu(name='View Character')
async def view_character(interaction: discord.Interaction, member: discord.Member):
    async with db_pool.acquire() as conn:
        character = await Character.fetch_by_user(conn, member.id, interaction.guild_id)

    if character is None:
        await interaction.response.send_message(
            emotive_message("User has no character assigned"),
            ephemeral = True)
    else:
        # Check if the user is an admin
        is_admin = interaction.user.guild_permissions.manage_guild

        if is_admin:
            # Show full information for admins
            await interaction.response.send_message(
                emotive_message(f"Identifier: {character.identifier},\nName: {character.name},\nLetter Limit: {character.letter_limit},\nLetter Count: {character.letter_count}"),
                ephemeral = True)
        else:
            # Show only identifier for non-admins
            await interaction.response.send_message(
                emotive_message(f"Identifier: {character.identifier}"),
                ephemeral = True)
                        
        
@tree.command(
    name="config-server",
    description="Start an interaction to set the server specific settings for this server"
)
@app_commands.default_permissions(manage_guild=True)
async def config_server(interaction: discord.Interaction):
    # Get the current settings, if any
    async with db_pool.acquire() as conn:
        server_config = await ServerConfig.fetch(conn, interaction.guild_id)

    if server_config is None:
        server_config = ServerConfig(guild_id = interaction.guild_id)

    if server_config.category_id is not None:
        server_config.category = discord.utils.get(interaction.guild.categories, id=server_config.category_id)
    else:
        server_config.category = None

    if server_config.admin_response_channel_id is not None:
        server_config.admin_response_channel = interaction.guild.get_channel(server_config.admin_response_channel_id)
    else:
        server_config.admin_response_channel = None

    await interaction.response.send_modal(ConfigServerModal(config_server_callback, server_config))    

async def config_server_callback(interaction: discord.Interaction,
                                 default_limit: Optional[str],
                                 letter_delay: Optional[str],
                                 channel_category: Optional[str],
                                 reset_time_str: Optional[str],
                                 admin_response_channel: Optional[str]):
    limit = None
    # Parse default limit as an int
    if default_limit is not None and len(default_limit) > 0:
        try:
            limit = int(default_limit)
        except ValueError:
            await interaction.response.send_message(
                emotive_message('Invalid Default Limit. Please enter a number.'),
                ephemeral=True)
            return

    delay = None
    # Parse letter delay as an int
    if letter_delay is not None and len(letter_delay) > 0:
        try:
            delay = int(letter_delay)
        except ValueError:
            await interaction.response.send_message(
                emotive_message('Invalid Letter Delay. Please enter a number.'),
                ephemeral=True)
            return

    # Parse reset time
    reset_time_obj = None
    if reset_time_str is not None and len(reset_time_str) > 0:
        try:
            from datetime import time as time_type
            time_parts = reset_time_str.split(':')
            if len(time_parts) != 2:
                raise ValueError("Time must be in HH:MM format")
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid time values")
            reset_time_obj = time_type(hour=hour, minute=minute)
        except (ValueError, IndexError) as e:
            await interaction.response.send_message(
                emotive_message('Invalid Reset Time. Please enter time in HH:MM format (e.g., 00:00).'),
                ephemeral=True)
            return

    category_id = None
    if channel_category is not None and len(channel_category) > 0:
        category = discord.utils.get(interaction.guild.categories, name=channel_category)
        
        # Check if category already exists
        if category:
            category_id = category.id
        else:
            # If not, send confirmation view
            view = Confirm()
            await interaction.response.send_message(
                emotive_message(f"Channel Category {channel_category} does not exist. Do you want to create it?"),
                view=view,
                ephemeral=True)

            await view.wait()
            interaction = view.interaction

            if view.value is None:
                # If not confirmed, abort
                await interaction.response.edit_message(
                    content=emotive_message("Server Configuration Timed Out"),
                    view=None)
                return

            elif view.value:
                # If confirmed, create category and get ID
                new_category = await interaction.guild.create_category(channel_category)
                category_id = new_category.id

            else:
                # If not confirmed, abort
                await interaction.response.edit_message(
                    content=emotive_message("Canceled Server Configuration"),
                    view=None)
                return

    # Parse admin response channel
    admin_response_channel_id = None
    if admin_response_channel is not None and len(admin_response_channel) > 0:
        channel = discord.utils.get(interaction.guild.text_channels, name=admin_response_channel)
        if channel:
            admin_response_channel_id = channel.id
        else:
            await interaction.response.send_message(
                emotive_message(f'Admin Response Channel "{admin_response_channel}" not found. Please check the channel name.'),
                ephemeral=True)
            return

    # Create object
    config = ServerConfig(
        guild_id=interaction.guild_id,
        default_limit=limit,
        letter_delay=delay,
        category_id=category_id,
        reset_time=reset_time_obj,
        admin_response_channel_id=admin_response_channel_id
    )

    # Verify values
    ok, message = config.verify()

    if not ok:
        await interaction.response.send_message(emotive_message(message), ephemeral=True)
        return

    # Upsert result
    async with db_pool.acquire() as conn:
        # Check if reset_time was changed
        old_config = await ServerConfig.fetch(conn, interaction.guild_id)
        reset_time_changed = (old_config is None or old_config.reset_time != reset_time_obj)

        await config.upsert(conn)

        # If reset_time was changed, cancel existing reset_counts tasks and schedule a new one
        if reset_time_changed and reset_time_obj is not None:
            # Delete all existing reset_counts tasks for this guild
            deleted_count = await HawkyTask.delete_by_type_and_guild(conn, "reset_counts", interaction.guild_id)

            # Calculate the next occurrence of the reset time
            now = datetime.now()
            next_reset = datetime.combine(now.date(), reset_time_obj)

            # If the time has already passed today, schedule for tomorrow
            if next_reset <= now:
                next_reset = datetime.combine(now.date() + timedelta(days=1), reset_time_obj)

            # Schedule the new reset task
            reset_task = HawkyTask(
                task="reset_counts",
                guild_id=interaction.guild_id,
                scheduled_time=next_reset
            )
            await reset_task.insert(conn)

            logger.info(f"Server config updated for guild {interaction.guild_id}. Reset time: {reset_time_obj.strftime('%H:%M')} UTC, next reset: {next_reset}")
            await interaction.response.send_message(
                emotive_message(f"Server Config Updated. Reset time changed to {reset_time_obj.strftime('%H:%M')} UTC. Next reset scheduled for {next_reset.strftime('%Y-%m-%d %H:%M:%S')} UTC"),
                ephemeral=True)
        else:
            logger.info(f"Server config updated for guild {interaction.guild_id}")
            await interaction.response.send_message(emotive_message("Server Config Updated"), ephemeral=True)

@tree.command(
    name="reset-counts",
    description="Reset daily counts for all characters manually"
)
@app_commands.default_permissions(manage_guild=True)
async def reset_counts(interaction: discord.Interaction):
    async with db_pool.acquire() as conn:
        # Reset letter counts
        await Character.reset_letter_counts(conn, interaction.guild_id)

        # Check if a reset_counts task already exists for this guild
        task_exists = await HawkyTask.exists_for_guild(conn, "reset_counts", interaction.guild_id)

        message = "Reset daily letter counts"

        if not task_exists:
            # Get the server config to find the reset time
            server_config = await ServerConfig.fetch(conn, interaction.guild_id)

            # Determine the reset time (default to midnight if not configured)
            from datetime import time as time_type
            reset_time = server_config.reset_time if server_config and server_config.reset_time else time_type(0, 0)

            # Calculate the next occurrence of the reset time
            now = datetime.now()
            next_reset = datetime.combine(now.date(), reset_time)

            # If the time has already passed today, schedule for tomorrow
            if next_reset <= now:
                next_reset = datetime.combine(now.date() + timedelta(days=1), reset_time)

            reset_task = HawkyTask(
                task="reset_counts",
                guild_id=interaction.guild_id,
                scheduled_time=next_reset
            )
            await reset_task.insert(conn)
            message += f" and scheduled automatic daily resets at {reset_time.strftime('%H:%M')} UTC (next reset: {next_reset.strftime('%Y-%m-%d %H:%M:%S')})"
            logger.info(f"Manual reset triggered for guild {interaction.guild_id}. Scheduled next reset at {next_reset}")
        else:
            logger.info(f"Manual reset triggered for guild {interaction.guild_id}. Auto-reset already scheduled")


    await interaction.response.send_message(emotive_message(message),
                                            ephemeral=True)
    
client.run(BOT_TOKEN)
