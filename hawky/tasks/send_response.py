from db import *
import discord


async def handle_send_response(client: discord.Client, conn: asyncpg.Connection, task: HawkyTask):
    """
    Handle a send_response task by fetching the response message and sending it to the original sender's channel.
    Similar to send_letter, but for replies to letters.
    """
    # Get the response message
    params = task.parameter.split(" ")
    response_channel_id = int(params[0])  # The channel where the response was written
    response_message_id = int(params[1])  # The ID of that message
    # Optional: original message info for admin responses
    original_message_channel_id = int(params[2]) if len(params) > 2 else None
    original_message_id = int(params[3]) if len(params) > 3 else None

    response_channel = await client.fetch_channel(response_channel_id)
    response_message = await response_channel.fetch_message(response_message_id)

    # Check if the recipient is an admin (identified by ADMIN: prefix)
    if task.recipient_identifier.startswith("ADMIN:"):
        # This is a response to an admin letter, send to admin response channel
        server_config = await ServerConfig.fetch(conn, task.guild_id)
        if server_config and server_config.admin_response_channel_id:
            channel = await client.fetch_channel(server_config.admin_response_channel_id)
            # Extract user ID from the admin identifier
            admin_user_id = int(task.recipient_identifier.split(":")[1])
            user = await client.fetch_user(admin_user_id)

            # Build message with link to original admin message if available
            start_str = f"{user.mention}\n"
            if original_message_channel_id and original_message_id:
                message_link = f"https://discord.com/channels/{task.guild_id}/{original_message_channel_id}/{original_message_id}"
                start_str += f"In response to: {message_link}\n\n"

            await channel.send(f"{start_str}{response_message.content}",
                             files=[await attch.to_file() for attch in response_message.attachments])
        # If no admin response channel configured, silently fail (or could log an error)
        return

    # Get the original sender (who will receive the response)
    original_sender = await Character.fetch_by_identifier(conn, task.recipient_identifier, task.guild_id)

    # Get Channel where the response should be sent (original sender's channel)
    channel = await client.fetch_channel(original_sender.channel_id)

    # Get User who is supposed to be pinged
    user = None
    if original_sender.user_id is not None:
        user = await client.fetch_user(original_sender.user_id)

    # Send response message
    start_str = f"{user.mention}\n" if user else ""
    await channel.send(f"{start_str}{response_message.content}",
                       files=[await attch.to_file() for attch in response_message.attachments])

    # Note: Responses are not logged to SentLetter table as they cannot be replied to
