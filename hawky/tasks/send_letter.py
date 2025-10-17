from db import *
import discord


async def 

async def handle_send_letter(client: discord.Client, conn: asyncpg.Connection, task: HawkyTask):
    # Get the recipient
    recipient = Character.fetch_by_identifier(conn, task.recipient_identifier, task.guild_id)

    # Get the message
    params = task.paramater.split(" ")
    source_channel_id = int(params[0]) # The channel where the message originated
    message_id = int(params[1]) # The ID of that message
    source_channel = await client.fetch_channel(source_channel_id)
    message = await source_channel.fetch_message(message_id)
    
    # Get Channel where the letter should be sent
    channel = client.fetch_channel(recipient.channel_id)

    # Get User who is supposed to be pinged
    user = None
    if recipient.user_id is not None:
        user = await client.fetch_user(recipient.user_id)
        
    channel = await channel

    # Send message
    start_str = f"{user.mention}\n" if user else ""
    await channel.send(f"{start_str}{message.content}",
                       files = [await attch.to_file() for attch in message.attachments])

    # Add message to table where it can be responded to (TODO)
