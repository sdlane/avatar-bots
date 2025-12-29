import discord
from discord import app_commands
from discord.ext import commands, tasks
from helpers import *
from views import *
import os
from dotenv import load_dotenv
from db import *
from datetime import datetime, timedelta
from tasks.send_letter import handle_send_letter

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# Task Handler
@tasks.loop(seconds=60)
async def process_hawky_tasks():
    """Process pending tasks from the HawkyTask table."""
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")

    try:
        # Get the next task that's due
        task = await HawkyTask.pop_next_task(conn, datetime.now())

        while task is not None:
            # Handle different task types
            if task.task == "send_letter":
                try:
                    await handle_send_letter(client, conn, task)
                    print(f"Successfully sent letter from {task.sender_identifier} to {task.recipient_identifier}")
                except Exception as e:
                    print(f"Error sending letter (task {task.id}): {e}")
            elif task.task == "reset_counts":
                try:
                    await handle_reset_counts(conn, task)
                    print(f"Successfully reset letter counts for guild {task.guild_id}")
                except Exception as e:
                    print(f"Error resetting counts (task {task.id}): {e}")
            else:
                print(f"Unknown task type: {task.task}")

            # Get the next task
            task = await HawkyTask.pop_next_task(conn, datetime.now())

    except Exception as e:
        print(f"Error processing tasks: {e}")
    finally:
        await conn.close()

async def handle_reset_counts(conn: asyncpg.Connection, task: HawkyTask):
    """
    Handle a reset_counts task by resetting letter counts for a guild
    and scheduling the next reset for midnight.
    """
    # Reset letter counts for the guild
    await Character.reset_letter_counts(conn, task.guild_id)

    # Calculate next midnight
    now = datetime.now()
    next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Schedule the next reset task
    next_task = HawkyTask(
        task="reset_counts",
        guild_id=task.guild_id,
        scheduled_time=next_midnight
    )
    await next_task.insert(conn)

    print(f"Scheduled next reset for guild {task.guild_id} at {next_midnight}")


# Public Commands
@client.event
async def on_ready():
    await tree.sync()
    process_hawky_tasks.start()  # Start the task processing loop
    print(f'We have logged in as {client.user}')

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
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
    sender = Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
    characters = Character.fetch_all(conn, interaction.guild_id)
    sender = await sender
    characters = await characters
    await conn.close()

    if sender.letter_limit is None or sender.letter_limit - sender.letter_count > 0:
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
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
    recipient = await Character.fetch_by_identifier(conn, recipient_identifier, sender.guild_id)

    # Get the ServerConfig for this server to get the letter delay
    config = ServerConfig.fetch(conn, sender.guild_id)
    
    # Confirm that the user wants to send a letter to this character
    # If there is, send confirmation checking whether it shoud connect this character to that channel
    view = Confirm()
    message_content = f"Are you sure you want to send this message to {recipient.name}?"
    if sender.letter_limit is not None:
        message_content = f"You have {sender.letter_limit - sender.letter_count} letters remaining today. " + message_content 
    await interaction.response.send_message(
        emotive_message(message_content),
        view=view,
        ephemeral = True)
    await view.wait()
    interaction = view.interaction

    if view.value is None:
        await interaction.response.send_message(
            emotive_message("Send letter timed out"),
            ephemeral = True)
        await conn.close()
        return
    elif not view.value:
        await interaction.response.send_message(
            emotive_message("Canceled send letter"),
            ephemeral=True)
        await conn.close()
        return

    # Schedule Send Message Task
    config = await config
    if config is not None and config.letter_delay is not None:
        scheduled_time = datetime.now() + timedelta(minutes=config.letter_delay)
    else:
        # If there is no letter delay, schedule it to go out with the next tick
        scheduled_time = datetime.now()
        
    task = HawkyTask(task = "send_letter",
                     recipient_identifier = recipient_identifier,
                     sender_identifier = sender.identifier,
                     parameter = f"{message.channel.id} {message.id}",
                     scheduled_time = scheduled_time,
                     guild_id = sender.guild_id)

    await task.insert(conn)
    
    # Update count
    sender.letter_count += 1
    await sender.upsert(conn)
    await conn.close()

    # Send confirmation
    await interaction.response.send_message(
        emotive_message(f"Message queued to send to {recipient.name}"), ephemeral=True)

        
@tree.command(
    name="check-letter-limit",
    description="Check your remaining daily letter allocation"
)
async def check_letter_limit(interaction: discord.Interaction):
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
    character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
    await conn.close()

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


# Member ID: 372159950576943116, Guild ID:  1229419428240822343

# Admin Commands
@tree.command(
    name="create-character",
    description="Create a new character in the DB and then start a configuration menu for that character"
)
@app_commands.describe(
    identifier="The identifier you want to use for the new character. Will be used as the channel name, must be unique for this server"
)
async def create_character(interaction: discord.Interaction, identifier: str):
    # Get server settings for this guild
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
    server_config = await ServerConfig.fetch(conn, interaction.guild_id)
    await conn.close()

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
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
    character = await Character.fetch_by_identifier(conn, identifier, interaction.guild_id)
    await conn.close()

    if character is not None:
        await interaction.response.send_message(
            emotive_message(f"A character with the identifier {identifier} already exists in the database, aborting."),
            ephemeral = True
        )
        return
    
    # Check if there's already a channel with this identifier in the specified category
    channel = discord.utils.get(category.channels, name=identifier)
    
    if channel is None:
        # If not, make the channel
        channel = await interaction.guild.create_text_channel(identifier, category=category)

    else:
        # If there is, send confirmation checking whether it shoud connect this character to that channel
        view = Confirm()
        await interaction.response.send_message(
            emotive_message(f"A channel called {identifier} already exists in the configured category. Would you like to connect this character to it?"),
            view=view,
            ephemeral = True)
        await view.wait()
        interaction = view.interaction
        
        if view.value is None:
            # If not confirmed, abort
            await interaction.response.send_message(
                emotive_message("Character Creation Timed Out"),
                ephemeral=True)
            return

        elif not view.value:
            # If not confirmed, abort
            await interaction.response.send_message(
                emotive_message("Canceled Create Character"),
                ephemeral=True)
            return


    # Create the character object
    character = Character(identifier=identifier,
                          name=identifier,
                          channel_id = channel.id,
                          letter_limit = server_config.default_limit,
                          guild_id = interaction.guild_id)

    # Write character to the database
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
    await character.upsert(conn)
    await conn.close()
    
    await interaction.response.send_message(
        emotive_message(f'Created character with identifier: {identifier}'), ephemeral=True)

@tree.command(
    name="remove-character",
    description="Remove a new character from the DB and its associated channel"
)
@app_commands.describe(
    identifier="The identifier of the character you want to remove"
)
async def remove_character(interaction: discord.Interaction, identifier: str):
    # Get the character from the database
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
    character = await Character.fetch_by_identifier(conn, identifier, interaction.guild_id)

    # If that character doesn't exist, abort
    if character is None:
        await conn.close()
        await interaction.response.send_message(
            emotive_message(f"There is no character with the identifier {identifier} in the database"),
            ephemeral = True)
        return

    # Delete the associated channel
    delete_channel = interaction.guild.get_channel(character.channel_id).delete()
    
    # Delete the character from the database
    delete_database = Character.delete(conn, character.id)

    await delete_channel
    await delete_database
    
    # Close connection
    await conn.close()
    
    # Send confirmation
    await interaction.response.send_message(
        emotive_message(f"Successfully deleted {identifier}"),
        ephemeral = True)
    

@tree.command(
    name="config-character",
    description="Configure the specified character, updating its entry in the database"
)
@app_commands.describe(
    identifier="The identifier of the character you want to configure"
)
async def config_character(interaction: discord.Interaction, identifier: str):
    # Get exisitng character entry
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
    character = await Character.fetch_by_identifier(conn, identifier, interaction.guild_id)
    await conn.close()
    
    # If it doesn't exist, send an error message
    if character is None:
        await interaction.response.send_message(
            emotive_message(f"No character with the identifier {identifier} exists"),
            ephemeral=True)
    else:
        # Otherwise, send the config
        await interaction.response.send_modal(ConfigCharacterModal(character))
    
    
@tree.context_menu(name='Assign Character')
async def assign_character(interaction: discord.Interaction, member: discord.Member):
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
    # Get the user's previous character
    old_character = Character.fetch_by_user(conn, member.id, interaction.guild_id)
    
    # Send menu with dropdown to select un-selected characters
    unowned_characters = Character.fetch_unowned(conn, interaction.guild_id)

    old_character = await old_character
    unowned_characters = await unowned_characters
    await conn.close()

    view = AssignCharacterView(old_character, unowned_characters, member.id)
    await interaction.response.send_message("Select a character", view=view, ephemeral=True)    

@tree.context_menu(name='View Character')
async def view_character(interaction: discord.Interaction, member: discord.Member):
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
    character = await Character.fetch_by_user(conn, member.id, interaction.guild_id)
    await conn.close()

    if character is None:
        await interaction.response.send_message(
            emotive_message("User has no character assigned"),
            ephemeral = True)
    else:
        await interaction.response.send_message(
            emotive_message(f"Identifier: {character.identifier},\nName: {character.name},\nLetter Limit: {character.letter_limit},\nLetter Count: {character.letter_count}"),
            ephemeral = True)
                        
        
@tree.command(
    name="config-server",
    description="Start an interaction to set the server specific settings for this server"
)
async def config_server(interaction: discord.Interaction):
    # Get the current settings, if any
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
    server_config = await ServerConfig.fetch(conn, interaction.guild_id)
    await conn.close()

    if server_config is None:
        server_config = ServerConfig(guild_id = interaction.guild_id)

    if server_config.category_id is not None:
        server_config.category = discord.utils.get(interaction.guild.categories, id=server_config.category_id)
    else:
        server_config.category = None
    
    await interaction.response.send_modal(ConfigServerModal(config_server_callback, server_config))    

async def config_server_callback(interaction: discord.Interaction,
                                 default_limit: Optional[str],
                                 letter_delay: Optioal[str],
                                 channel_category: Optional[str]):
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
            if view.value is None:
                # If not confirmed, abort
                interaction.respose.send_message(
                    emotive_message("Server Configuration Timed Out"),
                    ephemeral=True)
                return
            
            elif view.value:
                # If confirmed, create category and get ID
                new_category = await interaction.guild.create_category(channel_category)
                category_id = new_category.id
                interaction = view.interaction
                
            else:
                # If not confirmed, abort
                interaction.respose.send_message(
                    emotive_message("Canceled Server Configuration"),
                    ephemeral=True)
                return

    # Create object
    config = ServerConfig(
        guild_id=interaction.guild_id,
        default_limit=limit,
        letter_delay=delay,
        category_id=category_id
    )

    # Verify values
    ok, message = config.verify()

    if not ok:
        await interaction.response.send_message(emotive_message(message), ephemeral=True) 
        return
    
    # Upsert result
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
    await config.upsert(conn)
    await conn.close()
    await interaction.response.send_message(emotive_message("Server Config Updated"), ephemeral=True)

@tree.command(
    name="reset-counts",
    description="Reset daily counts for all characters manually"
)
async def reset_counts(interaction: discord.Interaction):
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")

    # Reset letter counts
    await Character.reset_letter_counts(conn, interaction.guild_id)

    # Check if a reset_counts task already exists for this guild
    task_exists = await HawkyTask.exists_for_guild(conn, "reset_counts", interaction.guild_id)

    message = "Reset daily letter counts"

    if not task_exists:
        # Schedule the next reset for midnight
        now = datetime.now()
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        reset_task = HawkyTask(
            task="reset_counts",
            guild_id=interaction.guild_id,
            scheduled_time=next_midnight
        )
        await reset_task.insert(conn)
        message += f" and scheduled automatic daily resets at midnight (next reset: {next_midnight.strftime('%Y-%m-%d %H:%M:%S')})"

    await conn.close()
    await interaction.response.send_message(emotive_message(message),
                                            ephemeral=True)
    
client.run(BOT_TOKEN)
