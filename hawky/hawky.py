import discord
from discord import app_commands
from discord.ext import commands
from helpers import *
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
    await interaction.response.send_message(message.content,
                                            files = [await attch.to_file() for attch in message.attachments],
                                            ephemeral=True)


@tree.command(
    name="check-letter-limit",
    description="Check your remaining daily letter allocation"
)
async def whistle(interaction: discord.Interaction):
    remaining_letters = 2
    letter_limit = 2
    await interaction.response.send_message(
        f'You have {remaining_letters} letters remaining out of a maximum of {letter_limit}', ephemeral=True)

    
# Admin Commands
client.run(BOT_TOKEN)
