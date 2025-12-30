import discord
from discord import ui
from helpers import *
from db import *
from typing import Optional, List
import handlers

# Adapted from examples: https://github.com/Rapptz/discord.py/blob/v2.6.4/examples/views/settings.py

class Confirm(ui.View):
    def __init__(self):
        super().__init__()
        self.value = None
        self.interaction = None

    # When the confirm button is pressed, set the inner value to `True` and
    # stop the View from listening to more input.
    # We also send the user an ephemeral message that we're confirming their choice.
    @ui.button(label='Confirm', style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.interaction = interaction
        self.stop()

    # This one is similar to the confirmation button except sets the inner value to `False`
    @ui.button(label='Cancel', style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.interaction = interaction
        self.stop()

class AssignCharacterDropdown(discord.ui.Select):
    def __init__(self, old_character: Character, unowned_characters: List[Character], user_id: int):
        options = []
        self.old_character = old_character
        self.user_id = user_id
        if old_character is not None:
            options.append(discord.SelectOption(label=old_character.identifier, default = True))
            options.append(discord.SelectOption(label="None"))
        else:
            options.append(discord.SelectOption(label="None", default = True))

        for character in unowned_characters:
            options.append(discord.SelectOption(label=character.identifier))
        
        super().__init__(min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await handlers.assign_character_callback(interaction,
                                                 self.values[0],
                                                 self.old_character,
                                                 self.user_id)

class AssignCharacterView(ui.View):
    def __init__(self, old_character: Character, unowned_characters: List[Character], user_id: int):        
        super().__init__()

        self.add_item(AssignCharacterDropdown(old_character, unowned_characters, user_id))

class SendLetterDropdown(discord.ui.Select):
    def __init__(self,
                 message: discord.Message,
                 sender: Character,
                 characters: List[Character],
                 handler):
        self.message = message
        self.sender = sender
        self.handler = handler
        options = [discord.SelectOption(label=character.identifier) for character in characters]       
        super().__init__(min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.handler(interaction,
                           self.message,
                           self.sender,
                           self.values[0])

class SendLetterView(ui.View):
    def __init__(self,
                 message: discord.Message,
                 sender: Character,
                 characters: List[Character],
                 handler):        
        super().__init__()

        self.add_item(SendLetterDropdown(message, sender, characters, handler))

        
class ConfigServerModal(ui.Modal, title="Configure Server"):
    default_limit = ui.TextInput(label='Default Limit', style=discord.TextStyle.short, required=False)
    letter_delay = ui.TextInput(label='Letter Delay', style=discord.TextStyle.short, required=False)
    channel_category = ui.TextInput(label='Character Channel Category', style=discord.TextStyle.short, required=False)
    reset_time = ui.TextInput(label='Reset Time (HH:MM) UTC', style=discord.TextStyle.short, required=False, placeholder='00:00')

    def __init__(self, callback, server_config):
        super().__init__()
        self.callback = callback
        self.server_config = server_config
        if self.server_config.default_limit is not None:
            self.default_limit.default = str(self.server_config.default_limit)
        if self.server_config.letter_delay is not None:
            self.letter_delay.default = str(self.server_config.letter_delay)
        if self.server_config.category is not None:
            self.channel_category.default = self.server_config.category.name
        if self.server_config.reset_time is not None:
            self.reset_time.default = self.server_config.reset_time.strftime('%H:%M')

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction,
                            self.default_limit.value,
                            self.letter_delay.value,
                            self.channel_category.value,
                            self.reset_time.value)
        
class ConfigCharacterModal(ui.Modal, title="Configure Character"):
    name = ui.TextInput(label='Public Character Name',  style=discord.TextStyle.short, required=True)
    limit = ui.TextInput(label='Daily Letter Limit', style=discord.TextStyle.short, required=False)
    count = ui.TextInput(label="Today's Letter Count", style=discord.TextStyle.short, required=False)

    def __init__(self, character):
        super().__init__()
        self.character = character

        if self.character.name is not None:
            self.name.default = str(self.character.name)

        if self.character.letter_limit is not None:
            self.limit.default = str(self.character.letter_limit)

        if self.character.letter_count is not None:
            self.count.default = str(self.character.letter_count)


    async def on_submit(self, interaction: discord.Interaction):
        await handlers.config_character_callback(interaction,
                                                 self.character,
                                                 self.limit.value,
                                                 self.count.value,
                                                 self.name.value)


class RemindMeModal(ui.Modal, title="Set Reminder"):
    time_input = ui.TextInput(
        label='Remind me in...',
        style=discord.TextStyle.short,
        placeholder='e.g., 30 minutes, 8 hours, 3 days',
        required=True
    )

    def __init__(self, callback, message):
        super().__init__()
        self.callback = callback
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction, self.message, self.time_input.value)


class SelectLetterDropdown(discord.ui.Select):
    def __init__(self, message: discord.Message, sent_letters: List, handler):
        self.message = message
        self.sent_letters = sent_letters
        self.handler = handler

        # Create options from sent letters - truncate message content to fit in label
        options = []
        for i, letter in enumerate(sent_letters):
            # Get the content and remove mention from the front
            content = letter.get('content', '')
            content = remove_mention(content) if content else ''

            # Get attachment information
            attachments = letter.get('attachments', [])

            # Generate preview
            if content:
                # Get first 80 characters of the letter content for the description
                letter_preview = content[:80]
                if len(content) > 80:
                    letter_preview += "..."
            elif attachments:
                # If no content but there are attachments, describe them
                if len(attachments) == 1:
                    att = attachments[0]
                    filename = att.filename if hasattr(att, 'filename') else 'file'
                    letter_preview = f"[Attachment: {filename}]"
                else:
                    letter_preview = f"[{len(attachments)} attachments]"
            else:
                letter_preview = "[No content]"

            # Format the sent time for the label
            sent_time = letter.get('sent_time')
            if sent_time:
                # Format as "MMM DD, HH:MM" (e.g., "14:30")
                time_label = sent_time.strftime('%H:%M')
            else:
                time_label = "Unknown time"

            # Use formatted time as label, preview as description
            label = f"Letter received @{time_label} UTC"
            description = letter_preview

            options.append(discord.SelectOption(
                label=label,
                description=description,
                value=str(i)  # Use index as value
            ))

        super().__init__(
            placeholder="Select a letter to respond to",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_index = int(self.values[0])
        selected_letter = self.sent_letters[selected_index]
        await self.handler(interaction, self.message, selected_letter)


class SelectLetterView(ui.View):
    def __init__(self, message: discord.Message, sent_letters: List, handler):
        super().__init__()
        self.add_item(SelectLetterDropdown(message, sent_letters, handler))



