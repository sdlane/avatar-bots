import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional
from helpers import *
from views import *
import os
import logging
from dotenv import load_dotenv
from db import *
from db import SpiritNexus
from datetime import datetime, timedelta
from tasks.send_letter import handle_send_letter
from tasks.remind_me import handle_remind_me
from tasks.send_response import handle_send_response
from herbalism import make_blend
from handlers import create_character_with_channel
from character_config import CharacterConfigManager
import re
import os

load_dotenv()

# Configure logging
logging.basicConfig(
    filename='hawky-log.txt',
    filemode='a',
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
    # Get the sender character
    async with db_pool.acquire() as conn:
        sender = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
        server_config = await ServerConfig.fetch(conn, interaction.guild_id)

    # Check if user is an admin without a character
    is_admin = interaction.user.guild_permissions.manage_guild
    if sender is None and is_admin and server_config and server_config.admin_response_channel_id:
        # Admin without character can send letters if admin response channel is configured
        await interaction.response.send_modal(SendLetterModal(send_letter_modal_callback, message, None))
    elif sender is None:
        # User has no character and isn't an admin or admin channel not configured
        await interaction.response.send_message(
            emotive_message("You don't have a character assigned!"),
            ephemeral=True)
    elif sender.letter_limit is None or sender.letter_limit - sender.letter_count > 0:
        await interaction.response.send_modal(SendLetterModal(send_letter_modal_callback, message, sender))
    else:
        await interaction.response.send_message(
            emotive_message("You have no letters remaining!"),
            ephemeral = True)

async def send_letter_modal_callback(interaction: discord.Interaction,
                                     message: discord.Message,
                                     sender: Character,
                                     recipient_identifier: str):
    """
    Callback for the SendLetterModal. Validates that the recipient exists,
    then calls send_letter_callback to show confirmation and send the letter.
    """
    # Verify that a character with this identifier exists (or an alias)
    async with db_pool.acquire() as conn:
        recipient = await Character.fetch_by_identifier(conn, recipient_identifier, interaction.guild_id)

        # If not found, check if it's an alias
        if recipient is None:
            alias_entry = await Alias.fetch_by_alias(conn, recipient_identifier, interaction.guild_id)
            if alias_entry is not None:
                # Found an alias, get the actual character
                recipient = await Character.fetch_by_id(conn, alias_entry.character_id)

    if recipient is None:
        await interaction.response.send_message(
            emotive_message(f"No character found with identifier '{recipient_identifier}'"),
            ephemeral=True)
        return

    # Defer the response to acknowledge the modal submission
    await interaction.response.defer(ephemeral=True)

    # Character exists, proceed with send_letter_callback using the character's actual identifier
    await send_letter_callback(interaction, message, sender, recipient, recipient_identifier)

DISCORD_MESSAGE_LIMIT = 2000


async def send_letter_callback(interaction: discord.Interaction,
                               message: discord.Message,
                               sender: Character,
                               recipient: Character,
                               recipient_identifier: str):
    # Get the characters for the sender and the recipient
    async with db_pool.acquire() as conn:
        guild_id = interaction.guild_id
        # recipient = await Character.fetch_by_identifier(conn, recipient_identifier, guild_id)

        # Check if adding the mention would exceed Discord's message limit
        mention_length = len(f"<@{recipient.user_id}>\n") if recipient.user_id else 0
        total_length = mention_length + len(message.content)
        if total_length > DISCORD_MESSAGE_LIMIT:
            await interaction.followup.send(
                emotive_message(f"Your message is too long! With the recipient mention, it would be {total_length} characters (limit is {DISCORD_MESSAGE_LIMIT}). Please shorten your message by at least {total_length - DISCORD_MESSAGE_LIMIT} characters."),
                ephemeral=True)
            return

        # Get the ServerConfig for this server to get the letter delay
        config = await ServerConfig.fetch(conn, guild_id)

        # Confirm that the user wants to send a letter to this character
        view = Confirm()
        message_content = f"Are you sure you want to send this message to {recipient_identifier}?"
        if sender is not None and sender.letter_limit is not None:
            message_content = f"You have {sender.letter_limit - sender.letter_count} letters remaining today. " + message_content
        await interaction.followup.send(
            emotive_message(message_content),
            view=view,
            ephemeral=True)
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
        if config is not None and config.letter_delay is not None:
            scheduled_time = datetime.now() + timedelta(minutes=config.letter_delay)
        else:
            # If there is no letter delay, schedule it to go out with the next tick
            scheduled_time = datetime.now()

        # Use a special identifier for admin letters
        sender_identifier = sender.identifier if sender else f"ADMIN:{interaction.user.id}"

        task = HawkyTask(task = "send_letter",
                         recipient_identifier = recipient.identifier,
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
        content=emotive_message(f"Message queued to send to {recipient_identifier}"), view=None)


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

        # Find all unresponded letters sent to this character within the last 24 hours
        window_start = datetime.now() - timedelta(hours=24)
        sent_letter_rows = await conn.fetch("""
            SELECT id, message_id, channel_id, sender_identifier, recipient_identifier,
                original_message_channel_id, original_message_id, has_response,
                guild_id, sent_time
            FROM SentLetter
            WHERE recipient_identifier = $1 AND guild_id = $2 AND has_response = FALSE
            AND sent_time >= $3
            ORDER BY sent_time DESC;
        """, sender.identifier, interaction.guild_id, window_start)

        if not sent_letter_rows:
            await interaction.response.send_message(
                emotive_message("No unreplied letters found for your character in the last 24 hours!"),
                ephemeral=True)
            return

        # Fetch the actual message content for each letter
        letters_with_content = []

        logger.debug(f"Character {sender.identifier}: has {len(sent_letter_rows)} unreplied letters.")
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
            logger.debug(f"Character {sender.identifier}: has {len(letters_with_content)} unreplied letters WITH content.")
            await send_response_confirmation(interaction, message, letters_with_content[0], sender, conn)
        else:
            # Multiple letters - show selection dialog
            logger.debug(f"Other branch. Character {sender.identifier}: has {len(letters_with_content)} unreplied letters WITH content.")
            view = SelectLetterView(message, letters_with_content, send_response_selection_callback)
            logger.debug(f"Created view in other branch.")
            await interaction.response.send_message(
                emotive_message(f"You have {len(letters_with_content)} unreplied letters. Please select which one to respond to:"),
                view=view,
                ephemeral=True)

            logger.debug(f"Created view in other branch.")


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
        # Check if adding the mention would exceed Discord's message limit
        # For responses, we need to check the recipient (original sender of the letter)
        recipient_identifier = selected_letter['sender_identifier']

        # Calculate mention length based on recipient type
        if recipient_identifier.startswith("ADMIN:"):
            # Admin recipient - mention will be added
            admin_user_id = recipient_identifier.split(":")[1]
            mention_length = len(f"<@{admin_user_id}>\n")
            # Admin responses also include a link to original message
            # Format: "In response to: https://discord.com/channels/{guild}/{channel}/{message}\n\n"
            # This adds roughly 80-100 characters
            mention_length += 100  # Conservative estimate for the link line
        else:
            # Character recipient - check if they have a user assigned
            original_sender = await Character.fetch_by_identifier(conn, recipient_identifier, interaction.guild_id)
            mention_length = len(f"<@{original_sender.user_id}>\n") if original_sender and original_sender.user_id else 0

        total_length = mention_length + len(message.content)
        if total_length > DISCORD_MESSAGE_LIMIT:
            error_msg = f"Your response is too long! With the recipient mention, it would be {total_length} characters (limit is {DISCORD_MESSAGE_LIMIT}). Please shorten your message by at least {total_length - DISCORD_MESSAGE_LIMIT} characters."
            if interaction.response.is_done():
                await interaction.edit_original_response(content=emotive_message(error_msg))
            else:
                await interaction.response.send_message(emotive_message(error_msg), ephemeral=True)
            return

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

        # Include original message info in parameter for admin response linking
        task = HawkyTask(
            task="send_response",
            recipient_identifier=selected_letter['sender_identifier'],
            sender_identifier=sender.identifier,
            parameter=f"{message.channel.id} {message.id} {selected_letter['original_message_channel_id']} {selected_letter['original_message_id']}",
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
    name="blend-herbs",
    description="Blend herbal ingredients to create a product"
)
@app_commands.describe(
    ingredients="Comma-separated list of ingredient item numbers (1-6 items, e.g. '5111,5419,5312')"
)
async def blend_herbs(
    interaction: discord.Interaction,
    ingredients: str
):
    """Blend herbal ingredients to create a product."""
    # Parse comma-separated list and strip whitespace
    ingredient_numbers = [num.strip() for num in ingredients.split(",") if num.strip()]

    logger.debug(f"blend_herbs: user={interaction.user.id}, ingredients={ingredient_numbers}")

    # Validate ingredient count
    if len(ingredient_numbers) == 0:
        logger.debug(f"blend_herbs: rejected - no ingredients provided")
        await interaction.response.send_message(
            "Please provide at least one ingredient.",
            ephemeral=True
        )
        return

    if len(ingredient_numbers) > 6:
        logger.debug(f"blend_herbs: rejected - too many ingredients ({len(ingredient_numbers)})")
        await interaction.response.send_message(
            f"Too many ingredients ({len(ingredient_numbers)}). Maximum is 6.",
            ephemeral=True
        )
        return

    async with db_pool.acquire() as conn:
        result = await make_blend(conn, ingredient_numbers)

    if not result.success:
        logger.debug(f"blend_herbs: blend failed - {result.error_message}")
        await interaction.response.send_message(
            result.error_message,
            ephemeral=True
        )
        return

    product = result.product
    logger.debug(f"blend_herbs: success - product={product.item_number} ({product.name}), type={product.product_type}, qty={result.quantity}")

    # Build the embed
    embed = discord.Embed(
        title=f"{product.product_type.title() if product.product_type else 'Product'}: {product.name or 'Unknown'}",
        color=discord.Color.green() if result.success else discord.Color.red()
    )

    embed.add_field(name="Item Number", value=product.item_number, inline=True)
    embed.add_field(name="Quantity", value=str(result.quantity), inline=True)
    embed.add_field(name="Type", value=product.product_type.title() if product.product_type else "Unknown", inline=True)

    if product.flavor_text:
        embed.add_field(name="Description", value=f"*{product.flavor_text}*", inline=False)

    if product.rules_text:
        embed.add_field(name="Effect", value=product.rules_text, inline=False)

    # Add box room instructions (or apply-herbs instruction if skip_prod)
    if product.skip_prod:
        embed.set_footer(
            text="This product cannot be found in the box room. Use the /apply-herbs command to apply it to a character."
        )
    else:
        box_type = product.product_type.title() if product.product_type else "Product"
        embed.set_footer(
            text=f"Find this in the box room in the envelope labeled '{box_type}: {product.item_number}'. "
                 f"Please let the GMs know if the folder is running low."
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(
    name="apply-herbs",
    description="Apply an herbal product to a character"
)
@app_commands.describe(
    item_number="The item number of the herbal product",
    product_type="The type of the herbal product (tea, salve, tincture, decoction, bath, incense)",
    character_identifier="The identifier of the character (optional, defaults to your character)"
)
@app_commands.choices(product_type=[
    app_commands.Choice(name="Tea", value="tea"),
    app_commands.Choice(name="Salve", value="salve"),
    app_commands.Choice(name="Tincture", value="tincture"),
    app_commands.Choice(name="Decoction", value="decoction"),
    app_commands.Choice(name="Bath", value="bath"),
    app_commands.Choice(name="Incense", value="incense"),
])
async def apply_herbs(
    interaction: discord.Interaction,
    item_number: str,
    product_type: app_commands.Choice[str],
    character_identifier: Optional[str] = None
):
    """Apply an herbal product to a character."""
    async with db_pool.acquire() as conn:
        # If no character specified, use the caller's character
        if character_identifier is None:
            character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
            if character is None:
                await interaction.response.send_message(
                    "You don't have a character assigned. Please specify a character identifier.",
                    ephemeral=True
                )
                return
        else:
            character = await Character.fetch_by_identifier(
                conn, character_identifier.strip(), interaction.guild_id
            )

        # Look up product by item_number AND product_type
        product = await Product.fetch_by_item_number_and_type(conn, item_number.strip(), product_type.value)

    # Handle character not found
    if character is None:
        logger.warning(
            f"apply-herbs failed: Character '{character_identifier}' not found. "
            f"User: {interaction.user.id}, Guild: {interaction.guild_id}"
        )
        await interaction.response.send_message(
            f"No character found with identifier '{character_identifier}'.",
            ephemeral=True
        )
        return

    # Handle product not found
    if product is None:
        logger.warning(
            f"apply-herbs failed: Product '{item_number}' with type '{product_type.value}' not found. "
            f"User: {interaction.user.id}, Guild: {interaction.guild_id}"
        )
        await interaction.response.send_message(
            f"No herbal product found with item number '{item_number}' and type '{product_type.name}'.",
            ephemeral=True
        )
        return

    # Get the channel
    channel = interaction.guild.get_channel(character.channel_id)
    if channel is None:
        channel = await client.fetch_channel(character.channel_id)

    # Get user for mention (if assigned)
    user = None
    if character.user_id is not None:
        user = await client.fetch_user(character.user_id)

    # Build the message
    mention_str = f"{user.mention}\n" if user else ""
    product_type = product.product_type.title() if product.product_type else "Product"

    message_content = (
        f"{mention_str}"
        f"You have been dosed with the following herbal product:\n\n"
        f"**{product_type}: {product.name or 'Unknown'}**\n"
        f"Item Number: {product.item_number}\n\n"
    )

    if product.flavor_text:
        message_content += f"*{product.flavor_text}*\n\n"

    if product.rules_text:
        message_content += f"{product.rules_text}"

    # Send to character channel (non-ephemeral)
    await channel.send(message_content)

    # Log the action
    logger.info(
        f"apply-herbs: User {interaction.user.id} applied product '{product.name}' "
        f"(#{item_number}) to character '{character_identifier}' in guild {interaction.guild_id}"
    )

    # Send ephemeral success to command user
    await interaction.response.send_message(
        f"Successfully applied {product.name or item_number} to {character.name or character_identifier}.",
        ephemeral=True
    )


@tree.command(
    name="analyze-evidence",
    description="Analyze evidence by its analysis number"
)
@app_commands.describe(
    analysis_number="The analysis number to look up"
)
async def analyze_evidence(interaction: discord.Interaction, analysis_number: str):
    """Analyze evidence by looking up its analysis number."""
    async with db_pool.acquire() as conn:
        evidence = await Evidence.fetch_by_analysis_number(conn, analysis_number.strip())

    if evidence is None:
        await interaction.response.send_message(
            f"No evidence found with analysis number '{analysis_number}'.",
            ephemeral=True
        )
        return

    # Check if user is an admin
    is_admin = interaction.user.guild_permissions.manage_guild

    # Build the embed
    embed = discord.Embed(
        title=f"Evidence Analysis: {evidence.analysis_number}",
        color=discord.Color.blue()
    )

    embed.add_field(name="Hint", value=evidence.hint or "No hint available", inline=False)

    if is_admin:
        embed.add_field(name="GM Notes", value=evidence.gm_notes or "No GM notes available", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


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

    # Check category_id is configured
    if server_config.category_id is None:
        await interaction.response.send_message(
            emotive_message("You need to set character channel in the server configuration before you can create a character"),
            ephemeral=True)
        return

    # Get the category object
    category = discord.utils.get(interaction.guild.categories, id=server_config.category_id)
    if category is None:
        await interaction.response.send_message(
            emotive_message("The configured category no longer exists. Please update server configuration."),
            ephemeral=True)
        return

    # Check if the character already exists in the database
    async with db_pool.acquire() as conn:
        existing_character = await Character.fetch_by_identifier(conn, identifier, interaction.guild_id)

    if existing_character is not None:
        await interaction.response.send_message(
            emotive_message(f"A character with the identifier {identifier} already exists in the database, aborting."),
            ephemeral=True)
        return

    # Check if there's already a channel with this identifier in the specified category
    existing_channel = discord.utils.get(category.channels, name=identifier)
    sent_confirmation = False

    if existing_channel is not None:
        # Channel exists but character doesn't - ask for confirmation
        sent_confirmation = True
        view = Confirm()
        await interaction.response.send_message(
            emotive_message(f"A channel called {identifier} already exists in the configured category. Would you like to connect this character to it?"),
            view=view,
            ephemeral=True)
        await view.wait()
        interaction = view.interaction

        if view.value is None:
            await interaction.response.edit_message(
                content=emotive_message("Character Creation Timed Out"),
                view=None)
            return

        elif not view.value:
            await interaction.response.edit_message(
                content=emotive_message("Canceled Create Character"),
                view=None)
            return

    # Use the shared handler to create the character with channel
    async with db_pool.acquire() as conn:
        success, message, character = await create_character_with_channel(
            conn=conn,
            guild=interaction.guild,
            identifier=identifier,
            name=identifier,
            letter_limit=server_config.default_limit,
            category_id=server_config.category_id
        )

    if not success:
        if sent_confirmation:
            await interaction.response.edit_message(
                content=emotive_message(message),
                view=None)
        else:
            await interaction.response.send_message(
                content=emotive_message(message),
                ephemeral=True)
        return

    logger.info(f"Created character with identifier: {identifier}")
    if sent_confirmation:
        await interaction.response.edit_message(
            content=emotive_message(f'Created character with identifier: {identifier}'),
            view=None)
    else:
        await interaction.response.send_message(
            content=emotive_message(f'Created character with identifier: {identifier}'),
            ephemeral=True)

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
        old_character = await Character.fetch_by_user(conn, member.id, interaction.guild_id)

    await interaction.response.send_modal(AssignCharacterModal(old_character, member.id))    

@tree.context_menu(name='View Character')
async def view_character(interaction: discord.Interaction, member: discord.Member):
    async with db_pool.acquire() as conn:
        character = await Character.fetch_by_user(conn, member.id, interaction.guild_id)

        # Check if the user is an admin
        is_admin = interaction.user.guild_permissions.manage_guild

        # Fetch aliases if admin
        aliases = []
        if is_admin and character is not None:
            aliases = await Alias.fetch_by_character_id(conn, character.id)

    if character is None:
        await interaction.response.send_message(
            emotive_message("User has no character assigned"),
            ephemeral = True)
    else:
        if is_admin:
            # Show full information for admins including aliases
            message_parts = [
                f"Identifier: {character.identifier}",
                f"Name: {character.name}",
                f"Letter Limit: {character.letter_limit}",
                f"Letter Count: {character.letter_count}"
            ]

            if aliases:
                alias_list = ", ".join([alias.alias for alias in aliases])
                message_parts.append(f"Aliases: {alias_list}")

            await interaction.response.send_message(
                emotive_message("\n".join(message_parts)),
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

@tree.command(
    name="add-alias",
    description="Add an alias identifier for a character"
)
@app_commands.describe(
    identifier="The identifier of the character to add an alias for",
    alias="The alias identifier to add"
)
@app_commands.default_permissions(manage_guild=True)
async def add_alias(interaction: discord.Interaction, identifier: str, alias: str):
    async with db_pool.acquire() as conn:
        # Get the character
        character = await Character.fetch_by_identifier(conn, identifier, interaction.guild_id)

        if character is None:
            await interaction.response.send_message(
                emotive_message(f"No character found with identifier '{identifier}'"),
                ephemeral=True)
            return

        # Check if the alias already exists as a character identifier
        existing_character = await Character.fetch_by_identifier(conn, alias, interaction.guild_id)
        if existing_character is not None:
            await interaction.response.send_message(
                emotive_message(f"Cannot add alias '{alias}' because a character with that identifier already exists"),
                ephemeral=True)
            return

        # Check if the alias already exists
        existing_alias = await Alias.exists(conn, alias, interaction.guild_id)
        if existing_alias:
            await interaction.response.send_message(
                emotive_message(f"Alias '{alias}' already exists"),
                ephemeral=True)
            return

        # Create the alias
        new_alias = Alias(
            character_id=character.id,
            alias=alias,
            guild_id=interaction.guild_id
        )
        await new_alias.insert(conn)

    logger.info(f"Added alias '{alias}' for character '{identifier}' in guild {interaction.guild_id}")
    await interaction.response.send_message(
        emotive_message(f"Added alias '{alias}' for character '{character.name}'"),
        ephemeral=True)

@tree.command(
    name="list-aliases",
    description="List all character aliases"
)
@app_commands.default_permissions(manage_guild=True)
async def list_aliases(interaction: discord.Interaction):
    async with db_pool.acquire() as conn:
        aliases = await Alias.fetch_all_by_guild(conn, interaction.guild_id)

        if not aliases:
            await interaction.response.send_message(
                emotive_message("No aliases found for this server"),
                ephemeral=True)
            return

        # Group aliases by character
        alias_by_char_id = {}
        for alias in aliases:
            if alias.character_id not in alias_by_char_id:
                alias_by_char_id[alias.character_id] = []
            alias_by_char_id[alias.character_id].append(alias.alias)

        # Fetch character names
        lines = []
        for char_id, alias_list in alias_by_char_id.items():
            character = await Character.fetch_by_id(conn, char_id)
            char_name = character.identifier if character else f"Unknown ({char_id})"
            aliases_str = ", ".join(alias_list)
            lines.append(f"**{char_name}**: {aliases_str}")

    message = "\n".join(sorted(lines))
    await interaction.response.send_message(
        emotive_message(f"**Aliases:**\n{message}"),
        ephemeral=True)

@tree.command(
    name="remove-alias",
    description="Remove an alias identifier"
)
@app_commands.describe(
    alias="The alias identifier to remove"
)
@app_commands.default_permissions(manage_guild=True)
async def remove_alias(interaction: discord.Interaction, alias: str):
    async with db_pool.acquire() as conn:
        # Check if the alias exists
        alias_entry = await Alias.fetch_by_alias(conn, alias, interaction.guild_id)

        if alias_entry is None:
            await interaction.response.send_message(
                emotive_message(f"No alias found with identifier '{alias}'"),
                ephemeral=True)
            return

        # Get the character for logging purposes
        character = await Character.fetch_by_id(conn, alias_entry.character_id)

        # Delete the alias
        await Alias.delete_by_alias(conn, alias, interaction.guild_id)

    logger.info(f"Removed alias '{alias}' from character '{character.identifier}' in guild {interaction.guild_id}")
    await interaction.response.send_message(
        emotive_message(f"Removed alias '{alias}' from character '{character.name}'"),
        ephemeral=True)

@tree.command(
    name="clear-characters",
    description="Delete all characters, aliases, and their channels"
)
@app_commands.default_permissions(manage_guild=True)
async def clear_characters(interaction: discord.Interaction):
    # Show confirmation dialog
    view = Confirm()
    await interaction.response.send_message(
        emotive_message("**WARNING:** This will delete ALL characters, aliases, and their Discord channels. This action cannot be undone. Are you sure?"),
        view=view,
        ephemeral=True)
    await view.wait()
    interaction = view.interaction

    if view.value is None:
        await interaction.response.edit_message(
            content=emotive_message("Clear characters timed out"),
            view=None)
        return

    if not view.value:
        await interaction.response.edit_message(
            content=emotive_message("Canceled clear characters"),
            view=None)
        return

    # User confirmed - proceed with deletion
    await interaction.response.edit_message(
        content=emotive_message("Clearing characters..."),
        view=None)

    async with db_pool.acquire() as conn:
        # Get all characters to find their channel IDs
        characters = await Character.fetch_all(conn, interaction.guild_id)

        # Delete all aliases first (foreign key constraint)
        aliases_deleted = await Alias.delete_all_by_guild(conn, interaction.guild_id)

        # Delete all characters from database
        characters_deleted = await Character.delete_all_by_guild(conn, interaction.guild_id)

    # Delete Discord channels
    channels_deleted = 0
    channels_failed = 0
    for character in characters:
        if character.channel_id:
            try:
                channel = interaction.guild.get_channel(character.channel_id)
                if channel:
                    await channel.delete()
                    channels_deleted += 1
            except Exception as e:
                logger.error(f"Failed to delete channel {character.channel_id}: {e}")
                channels_failed += 1

    # Build summary
    summary_parts = [f"{characters_deleted} character(s) deleted"]
    if aliases_deleted > 0:
        summary_parts.append(f"{aliases_deleted} alias(es) deleted")
    if channels_deleted > 0:
        summary_parts.append(f"{channels_deleted} channel(s) deleted")
    if channels_failed > 0:
        summary_parts.append(f"{channels_failed} channel(s) failed to delete")

    summary = ", ".join(summary_parts)
    logger.warning(f"clear-characters for guild {interaction.guild_id}: {summary}")

    await interaction.edit_original_response(
        content=emotive_message(f"Clear complete: {summary}"))

@tree.command(
    name="load-characters-config",
    description="Load characters and aliases from a YAML configuration file"
)
@app_commands.describe(
    config_file="Path to the config file (default: characters_config.yaml)"
)
@app_commands.default_permissions(manage_guild=True)
async def load_characters_config(interaction: discord.Interaction, config_file: str = "characters_config.yaml"):
    # Defer response since this may take time for many characters
    await interaction.response.defer(ephemeral=True)

    # Resolve the config file path relative to the hawky directory
    hawky_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(hawky_dir, config_file)

    # Check if file exists
    if not os.path.exists(config_path):
        await interaction.followup.send(
            emotive_message(f"Configuration file not found: {config_file}"),
            ephemeral=True)
        return

    # Read the YAML file
    try:
        with open(config_path, 'r') as f:
            config_yaml = f.read()
    except Exception as e:
        await interaction.followup.send(
            emotive_message(f"Error reading configuration file: {e}"),
            ephemeral=True)
        return

    # Import the configuration
    async with db_pool.acquire() as conn:
        success, message, stats = await CharacterConfigManager.import_config(
            conn=conn,
            guild_id=interaction.guild_id,
            config_yaml=config_yaml,
            guild=interaction.guild
        )

    if success:
        logger.info(f"Config import for guild {interaction.guild_id}: {stats.characters_created} created, "
                    f"{stats.characters_skipped} skipped, {stats.aliases_created} aliases")
        await interaction.followup.send(
            emotive_message(f"Configuration imported successfully!\n\n{message}"),
            ephemeral=True)
    else:
        logger.error(f"Config import failed for guild {interaction.guild_id}: {message}")
        await interaction.followup.send(
            emotive_message(f"Configuration import failed: {message}"),
            ephemeral=True)

# Spirit Nexus Admin Commands
@tree.command(
    name="create-nexus",
    description="[Admin] Create a new spirit nexus at a territory"
)
@app_commands.describe(
    identifier="Unique identifier for the nexus (e.g., 'north-pole')",
    territory_id="The territory where the nexus is located",
    health="Initial health of the nexus (default: 5)"
)
@app_commands.default_permissions(manage_guild=True)
async def create_nexus(
    interaction: discord.Interaction,
    identifier: str,
    territory_id: str,
    health: int = 5
):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Check if nexus with this identifier already exists
        existing = await SpiritNexus.fetch_by_identifier(conn, identifier, interaction.guild_id)
        if existing:
            await interaction.followup.send(
                f"A spirit nexus with identifier '{identifier}' already exists.",
                ephemeral=True
            )
            return

        # Create the nexus
        nexus = SpiritNexus(
            identifier=identifier,
            health=health,
            territory_id=territory_id,
            guild_id=interaction.guild_id
        )

        ok, error = nexus.verify()
        if not ok:
            await interaction.followup.send(f"Invalid nexus data: {error}", ephemeral=True)
            return

        await nexus.upsert(conn)

    logger.info(f"Admin {interaction.user.name} created spirit nexus '{identifier}' at {territory_id} with health {health}")
    await interaction.followup.send(
        f"Created spirit nexus **{identifier}** at territory **{territory_id}** with health **{health}**."
    )


@tree.command(
    name="view-nexus",
    description="[Admin] View details of a spirit nexus"
)
@app_commands.describe(
    identifier="The identifier of the nexus to view"
)
@app_commands.default_permissions(manage_guild=True)
async def view_nexus(interaction: discord.Interaction, identifier: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        nexus = await SpiritNexus.fetch_by_identifier(conn, identifier, interaction.guild_id)

    if nexus is None:
        await interaction.followup.send(
            f"No spirit nexus found with identifier '{identifier}'.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title=f"Spirit Nexus: {nexus.identifier}",
        color=discord.Color.purple()
    )
    embed.add_field(name="Health", value=str(nexus.health), inline=True)
    embed.add_field(name="Territory", value=nexus.territory_id, inline=True)
    embed.add_field(name="Internal ID", value=str(nexus.id), inline=True)

    await interaction.followup.send(embed=embed)


@tree.command(
    name="edit-nexus",
    description="[Admin] Edit an existing spirit nexus"
)
@app_commands.describe(
    identifier="The identifier of the nexus to edit",
    health="New health value (can be negative)",
    territory_id="New territory location",
    new_identifier="New identifier for the nexus"
)
@app_commands.default_permissions(manage_guild=True)
async def edit_nexus(
    interaction: discord.Interaction,
    identifier: str,
    health: Optional[int] = None,
    territory_id: Optional[str] = None,
    new_identifier: Optional[str] = None
):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        nexus = await SpiritNexus.fetch_by_identifier(conn, identifier, interaction.guild_id)

        if nexus is None:
            await interaction.followup.send(
                f"No spirit nexus found with identifier '{identifier}'.",
                ephemeral=True
            )
            return

        # Check if new_identifier conflicts with existing
        if new_identifier and new_identifier != identifier:
            existing = await SpiritNexus.fetch_by_identifier(conn, new_identifier, interaction.guild_id)
            if existing:
                await interaction.followup.send(
                    f"A spirit nexus with identifier '{new_identifier}' already exists.",
                    ephemeral=True
                )
                return

        # Apply updates
        changes = []
        if health is not None:
            changes.append(f"health: {nexus.health} -> {health}")
            nexus.health = health
        if territory_id is not None:
            changes.append(f"territory: {nexus.territory_id} -> {territory_id}")
            nexus.territory_id = territory_id
        if new_identifier is not None:
            changes.append(f"identifier: {nexus.identifier} -> {new_identifier}")
            # Delete old and create new since identifier is part of unique constraint
            await SpiritNexus.delete(conn, identifier, interaction.guild_id)
            nexus.identifier = new_identifier
            nexus.id = None  # Reset ID so it gets a new one

        if not changes:
            await interaction.followup.send(
                "No changes specified.",
                ephemeral=True
            )
            return

        ok, error = nexus.verify()
        if not ok:
            await interaction.followup.send(f"Invalid nexus data: {error}", ephemeral=True)
            return

        await nexus.upsert(conn)

    logger.info(f"Admin {interaction.user.name} edited spirit nexus '{identifier}': {', '.join(changes)}")
    await interaction.followup.send(f"Updated spirit nexus: {', '.join(changes)}")


@tree.command(
    name="delete-nexus",
    description="[Admin] Delete a spirit nexus"
)
@app_commands.describe(
    identifier="The identifier of the nexus to delete"
)
@app_commands.default_permissions(manage_guild=True)
async def delete_nexus(interaction: discord.Interaction, identifier: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        nexus = await SpiritNexus.fetch_by_identifier(conn, identifier, interaction.guild_id)

        if nexus is None:
            await interaction.followup.send(
                f"No spirit nexus found with identifier '{identifier}'.",
                ephemeral=True
            )
            return

        deleted = await SpiritNexus.delete(conn, identifier, interaction.guild_id)

    if deleted:
        logger.info(f"Admin {interaction.user.name} deleted spirit nexus '{identifier}'")
        await interaction.followup.send(f"Deleted spirit nexus **{identifier}**.")
    else:
        await interaction.followup.send(
            f"Failed to delete spirit nexus '{identifier}'.",
            ephemeral=True
        )


@tree.command(
    name="list-nexi",
    description="[Admin] List all spirit nexuses"
)
@app_commands.default_permissions(manage_guild=True)
async def list_nexi(interaction: discord.Interaction):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        nexuses = await SpiritNexus.fetch_all(conn, interaction.guild_id)

    if not nexuses:
        await interaction.followup.send(
            "No spirit nexuses found.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="Spirit Nexuses",
        color=discord.Color.purple()
    )

    for nexus in nexuses:
        embed.add_field(
            name=nexus.identifier,
            value=f"Health: {nexus.health}\nTerritory: {nexus.territory_id}",
            inline=True
        )

    await interaction.followup.send(embed=embed)


# Herbalism Admin Commands
@tree.command(
    name="view-product",
    description="[Admin] View details of an herbal product"
)
@app_commands.describe(
    item_number="The item number of the product",
    product_type="The type of the herbal product"
)
@app_commands.choices(product_type=[
    app_commands.Choice(name="Tea", value="tea"),
    app_commands.Choice(name="Salve", value="salve"),
    app_commands.Choice(name="Tincture", value="tincture"),
    app_commands.Choice(name="Decoction", value="decoction"),
    app_commands.Choice(name="Bath", value="bath"),
    app_commands.Choice(name="Incense", value="incense"),
])
@app_commands.default_permissions(manage_guild=True)
async def view_product(
    interaction: discord.Interaction,
    item_number: str,
    product_type: app_commands.Choice[str]
):
    """View details of an herbal product."""
    async with db_pool.acquire() as conn:
        product = await Product.fetch_by_item_number_and_type(conn, item_number.strip(), product_type.value)

    if product is None:
        await interaction.response.send_message(
            f"No product found with item number '{item_number}' and type '{product_type.name}'.",
            ephemeral=True
        )
        return

    # Build the embed (matching /blend-herbs output format)
    embed = discord.Embed(
        title=f"{product.product_type.title() if product.product_type else 'Product'}: {product.name or 'Unknown'}",
        color=discord.Color.green()
    )

    embed.add_field(name="Item Number", value=product.item_number, inline=True)
    embed.add_field(name="Quantity", value="1", inline=True)
    embed.add_field(name="Type", value=product.product_type.title() if product.product_type else "Unknown", inline=True)

    if product.flavor_text:
        embed.add_field(name="Description", value=f"*{product.flavor_text}*", inline=False)

    if product.rules_text:
        embed.add_field(name="Effect", value=product.rules_text, inline=False)

    # Add box room instructions (or apply-herbs instruction if skip_prod)
    if product.skip_prod:
        embed.set_footer(
            text="This product cannot be found in the box room. Use the /apply-herbs command to apply it to a character."
        )
    else:
        box_type = product.product_type.title() if product.product_type else "Product"
        embed.set_footer(
            text=f"Find this in the box room in the envelope labeled '{box_type}: {product.item_number}'. "
                 f"Please let the GMs know if the folder is running low."
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(
    name="list-failed-blends",
    description="[Admin] List all failed blend (ruined product) mappings"
)
@app_commands.default_permissions(manage_guild=True)
async def list_failed_blends(interaction: discord.Interaction):
    """List all failed blend mappings."""
    async with db_pool.acquire() as conn:
        failed_blends = await FailedBlend.fetch_all(conn)

    if not failed_blends:
        await interaction.response.send_message(
            "No failed blend mappings found.",
            ephemeral=True
        )
        return

    # Build the embed
    embed = discord.Embed(
        title="Failed Blend Mappings",
        description="These are the ruined products returned when a blend fails for each product type.",
        color=discord.Color.orange()
    )

    for fb in failed_blends:
        # Fetch the product to get its name
        async with db_pool.acquire() as conn:
            product = await Product.fetch_by_item_number_and_type(conn, fb.product_item_number, fb.product_type)

        product_name = product.name if product else "Unknown"
        embed.add_field(
            name=fb.product_type.title(),
            value=f"#{fb.product_item_number} - {product_name}",
            inline=True
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(
    name="view-ingredient",
    description="[Admin] View details of an herbal ingredient"
)
@app_commands.describe(
    item_number="The item number of the ingredient"
)
@app_commands.default_permissions(manage_guild=True)
async def view_ingredient(
    interaction: discord.Interaction,
    item_number: str
):
    """View details of an herbal ingredient."""
    async with db_pool.acquire() as conn:
        ingredient = await Ingredient.fetch_by_item_number(conn, item_number.strip())

    if ingredient is None:
        await interaction.response.send_message(
            f"No ingredient found with item number '{item_number}'.",
            ephemeral=True
        )
        return

    # Build the embed
    embed = discord.Embed(
        title=f"Ingredient: {ingredient.name or 'Unknown'}",
        color=discord.Color.blue()
    )

    embed.add_field(name="Item Number", value=ingredient.item_number, inline=True)
    embed.add_field(name="Rarity", value=ingredient.rarity or "Unknown", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)  # Spacer

    if ingredient.primary_chakra:
        primary_strength = f" ({ingredient.primary_chakra_strength})" if ingredient.primary_chakra_strength else ""
        embed.add_field(name="Primary Chakra", value=f"{ingredient.primary_chakra}{primary_strength}", inline=True)

    if ingredient.secondary_chakra:
        secondary_strength = f" ({ingredient.secondary_chakra_strength})" if ingredient.secondary_chakra_strength else ""
        embed.add_field(name="Secondary Chakra", value=f"{ingredient.secondary_chakra}{secondary_strength}", inline=True)

    if ingredient.primary_chakra or ingredient.secondary_chakra:
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Spacer

    properties_list = ingredient.get_properties_list()
    if properties_list:
        embed.add_field(name="Properties", value=", ".join(properties_list), inline=False)

    if ingredient.flavor_text:
        embed.add_field(name="Description", value=f"*{ingredient.flavor_text}*", inline=False)

    if ingredient.rules_text:
        embed.add_field(name="Rules", value=ingredient.rules_text, inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(
    name="view-recipe",
    description="[Admin] View recipes for an herbal product"
)
@app_commands.describe(
    item_number="The item number of the product",
    product_type="The type of the herbal product"
)
@app_commands.choices(product_type=[
    app_commands.Choice(name="Tea", value="tea"),
    app_commands.Choice(name="Salve", value="salve"),
    app_commands.Choice(name="Tincture", value="tincture"),
    app_commands.Choice(name="Decoction", value="decoction"),
    app_commands.Choice(name="Bath", value="bath"),
    app_commands.Choice(name="Incense", value="incense"),
])
@app_commands.default_permissions(manage_guild=True)
async def view_recipe(
    interaction: discord.Interaction,
    item_number: str,
    product_type: app_commands.Choice[str]
):
    """View recipes for an herbal product."""
    async with db_pool.acquire() as conn:
        # Fetch the product first to show its name
        product = await Product.fetch_by_item_number_and_type(conn, item_number.strip(), product_type.value)

        # Fetch subset recipes
        subset_recipes = await SubsetRecipe.fetch_by_product(conn, item_number.strip(), product_type.value)

        # Fetch constraint recipes
        constraint_recipes = await ConstraintRecipe.fetch_by_product(conn, item_number.strip(), product_type.value)

    if not subset_recipes and not constraint_recipes:
        product_name = f" ({product.name})" if product and product.name else ""
        await interaction.response.send_message(
            f"No recipes found for {product_type.name} #{item_number}{product_name}.",
            ephemeral=True
        )
        return

    # Build the embed
    product_name = product.name if product and product.name else "Unknown"
    embed = discord.Embed(
        title=f"Recipes for {product_type.name}: {product_name} (#{item_number})",
        color=discord.Color.gold()
    )

    # Add subset recipes
    if subset_recipes:
        for i, recipe in enumerate(subset_recipes, 1):
            ingredients_str = ", ".join(recipe.ingredients) if recipe.ingredients else "None"
            value = f"**Ingredients:** {ingredients_str}\n**Quantity Produced:** {recipe.quantity_produced}"
            embed.add_field(
                name=f"Subset Recipe #{i}",
                value=value,
                inline=False
            )

    # Add constraint recipes
    if constraint_recipes:
        for i, recipe in enumerate(constraint_recipes, 1):
            constraints = []

            if recipe.ingredients:
                ingredients_str = ", ".join(recipe.ingredients)
                constraints.append(f"**Ingredients:** {ingredients_str}")

            if recipe.primary_chakra:
                boon_str = f" ({recipe.primary_is_boon})" if recipe.primary_is_boon else ""
                constraints.append(f"**Primary Chakra:** {recipe.primary_chakra}{boon_str}")

            if recipe.secondary_chakra:
                boon_str = f" ({recipe.secondary_is_boon})" if recipe.secondary_is_boon else ""
                constraints.append(f"**Secondary Chakra:** {recipe.secondary_chakra}{boon_str}")

            if recipe.tier is not None:
                constraints.append(f"**Tier:** {recipe.tier}")

            constraints.append(f"**Quantity Produced:** {recipe.quantity_produced}")

            value = "\n".join(constraints) if constraints else "No constraints"
            embed.add_field(
                name=f"Constraint Recipe #{i}",
                value=value,
                inline=False
            )

    # Add summary footer
    total_recipes = len(subset_recipes) + len(constraint_recipes)
    embed.set_footer(text=f"Total: {len(subset_recipes)} subset recipe(s), {len(constraint_recipes)} constraint recipe(s)")

    await interaction.response.send_message(embed=embed, ephemeral=True)


client.run(BOT_TOKEN)
