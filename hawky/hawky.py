import discord
from discord import app_commands
from discord.ext import commands
from helpers import *
from views import *
import os
from dotenv import load_dotenv
from db import *

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')

intents = discord.Intents.default()
intents.message_content = True
 
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# Public Commands
@client.event
async def on_ready():
    await tree.sync()
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
    # Get Channel where it should be sent
    # Get the channel ID
    # Get the channel with discord bot
    channel = client.fetch_channel(1425476551918485534)

    # Get User who is supposed to be pinged
    # Get the user ID
    # Get the user object
    user = client.fetch_user(372159950576943116)

    channel = await channel
    user = await user
    start_str = f"{user.mention}\n" if user else ""
    message = await channel.send(f"{start_str}{message.content}",
                                 files = [await attch.to_file() for attch in message.attachments])
    await interaction.response.send_message(
        emotive_message(f"Message sent to {channel.name}"), ephemeral=True)
    
@tree.command(
    name="check-letter-limit",
    description="Check your remaining daily letter allocation"
)
async def whistle(interaction: discord.Interaction):
    remaining_letters = 2
    letter_limit = 2
    await interaction.response.send_message(
        emotive_message(f'You have {remaining_letters} letters remaining out of a maximum of {letter_limit}'),
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
    # Get exisitng character entry w
    await interaction.response.send_modal(ConfigCharacterModal())
    

@tree.context_menu(name='Assign Character')
async def assign_character(interaction: discord.Interaction, member: discord.Member):
    # For now, I'm using this to get info for testing other commands/figuring out datatypes, consider it a placeholder with a use
    await interaction.response.send_message(
        f'Member ID: {member.id}, Guild ID:  {interaction.guild_id}, Channel ID: {interaction.channel_id}, Category ID: {interaction.channel.category_id}', ephemeral=True)

    # Get the user's previous character
    
    # Send menu with dropdown to select un-selected characters

    # Get the response

    # When the response has been processed check if the value is the same as the previous value
    # If so, we are done
    # If not, check whether user had a character before
    # If so, remove them from the associated channel

    # Add them to the new channel

    # Send confirmation
    

    
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
                                 default_limit: Optionak[str],
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

client.run(BOT_TOKEN)
