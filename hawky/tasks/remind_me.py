from db import *
import discord


async def handle_remind_me(client: discord.Client, conn: asyncpg.Connection, task: HawkyTask):
    """
    Handle a remind_me task by sending a message with a link to the original message.
    """
    # Get the message details from the parameter
    params = task.parameter.split(" ")
    guild_id = int(params[0])
    channel_id = int(params[1])
    message_id = int(params[2])

    # Get the user to remind
    user = await client.fetch_user(int(task.recipient_identifier))

    # Construct the message link
    message_link = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"

    # Try to send a DM to the user
    try:
        await user.send(f"Reminder! You asked to be reminded about this message:\n{message_link}")
    except discord.Forbidden:
        # If DM fails, try to send in the original channel
        channel = await client.fetch_channel(channel_id)
        await channel.send(f"{user.mention} Reminder! You asked to be reminded about this message:\n{message_link}")
