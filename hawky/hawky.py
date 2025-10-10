import discord
from discord import app_commands
from discord.ext import commands
from helpers import *
from views import *
import os
from dotenv import load_dotenv

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
        f"Confirm, message sent to {channel.name} with id {message.id}", ephemeral=True)
    
@tree.command(
    name="check-letter-limit",
    description="Check your remaining daily letter allocation"
)
async def whistle(interaction: discord.Interaction):
    remaining_letters = 2
    letter_limit = 2
    await interaction.response.send_message(
        f'You have {remaining_letters} letters remaining out of a maximum of {letter_limit}', ephemeral=True)


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
    # Create entry in character table in database
    # If entry already exists for identifier on this guild, abort with error message

    # It's a new character so create a channel for it
    # Get the category ID that the characters should be created in from server settings
    # If it exists, use the category ID to get the actual category object
    category = discord.utils.get(interaction.guild.categories, id=1425476275719377006)

    # Use that category object and the identifier to create a channel
    channel = await interaction.guild.create_text_channel(identifier, category=category)

    # Send confirmation that the character was created and start configure character interaction
    await interaction.response.send_message(
        f'Creating character with identifier: {identifier}', ephemeral=True)


@tree.command(
    name="config-character",
    description="Configure the specified character, updating its entry in the database"
)
@app_commands.describe(
    identifier="The identifier of the character you want to configure"
)
async def create_character(interaction: discord.Interaction, identifier: str):
    await interaction.response.send_modal(ConfigCharacterModal())
    

@tree.context_menu(name='Assign Character')
async def assign_character(interaction: discord.Interaction, member: discord.Member):
    # For now, I'm using this to get info for testing other commands/figuring out datatypes, consider it a placeholder with a use
    await interaction.response.send_message(
        f'Member ID: {member.id}, Guild ID:  {interaction.guild_id}, Channel ID: {interaction.channel_id}, Category ID: {interaction.channel.category_id}', ephemeral=True)

@tree.command(
    name="config-server",
    description="Start an interaction to set the server specific settings for this server"
)
async def config_server(interaction: discord.Interaction):
    await interaction.response.send_modal(ConfigServerModal())

client.run(BOT_TOKEN)
