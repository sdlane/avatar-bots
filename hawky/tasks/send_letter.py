from db import *
import discord
from datetime import datetime


async def handle_send_letter(client: discord.Client, conn: asyncpg.Connection, task: HawkyTask):
    """
    Handle a send_letter task by fetching the original message and sending it to the recipient's channel.
    """
    # Get the recipient
    recipient = await Character.fetch_by_identifier(conn, task.recipient_identifier, task.guild_id)

    # Get the message
    params = task.parameter.split(" ")
    source_channel_id = int(params[0])  # The channel where the message originated
    message_id = int(params[1])  # The ID of that message
    source_channel = await client.fetch_channel(source_channel_id)
    message = await source_channel.fetch_message(message_id)

    # Get Channel where the letter should be sent
    channel = await client.fetch_channel(recipient.channel_id)

    # Get User who is supposed to be pinged
    user = None
    if recipient.user_id is not None:
        user = await client.fetch_user(recipient.user_id)

    # Send message
    start_str = f"{user.mention}\n" if user else ""
    sent_message = await channel.send(f"{start_str}{message.content}",
                                      files=[await attch.to_file() for attch in message.attachments])

    # Log the sent letter to the database
    sent_letter = SentLetter(
        message_id=sent_message.id,
        channel_id=channel.id,
        sender_identifier=task.sender_identifier,
        recipient_identifier=task.recipient_identifier,
        original_message_channel_id=source_channel_id,
        original_message_id=message_id,
        has_response=False,
        guild_id=task.guild_id,
        sent_time=datetime.now()
    )
    await sent_letter.insert(conn)
