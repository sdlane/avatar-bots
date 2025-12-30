import discord
from discord import app_commands
from discord.ext import commands, tasks
from helpers import *
import os
import logging
from dotenv import load_dotenv
from db import *

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - Iroh Logging - %(levelname)s - %(message)s'
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
    logger.info(f'We have logged in as {client.user}')

@tree.command(
    name="advice",
    description="Receive wisdom from Uncle Iroh"
)
async def advice(interaction: discord.Interaction):
    await interaction.response.send_message(get_emote_text())


client.run(BOT_TOKEN)
