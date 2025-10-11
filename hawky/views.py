import discord
from discord import ui
from helpers import *

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


class ConfigServerModal(ui.Modal, title="Configure Server"):
    default_limit = ui.TextInput(label='Default Limit', style=discord.TextStyle.short, required=False)
    letter_delay = ui.TextInput(label='Letter Delay', style=discord.TextStyle.short, required=False)
    channel_category = ui.TextInput(label='Character Channel Category', style=discord.TextStyle.short, required=False)
    
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

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction,
                            self.default_limit.value,
                            self.letter_delay.value,
                            self.channel_category.value)
        
class ConfigCharacterModal(ui.Modal, title="Configure Character"):
    name = ui.TextInput(label='Public Character Name',  style=discord.TextStyle.short, required=False)
    limit = ui.TextInput(label='Daily Letter Limit', style=discord.TextStyle.short, required=False)
    count = ui.TextInput(label="Today's Letter Count", style=discord.TextStyle.short, required=False)

    def __init__(self):
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(emotive_message("Character Confirmation Updated"), ephemeral=True)
