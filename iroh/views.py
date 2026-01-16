"""
Discord UI components (modals, views, buttons) for Iroh wargame bot.
"""
import discord
from typing import Optional
from db import Territory, UnitType, PlayerResources, Character, WargameConfig
import logging

logger = logging.getLogger(__name__)


class EditTerritoryModal(discord.ui.Modal, title="Edit Territory"):
    """Modal for editing territory properties."""

    def __init__(self, territory: Territory, db_pool):
        super().__init__()
        self.territory = territory
        self.db_pool = db_pool

        # Name field
        self.name_input = discord.ui.TextInput(
            label="Name",
            placeholder="Optional display name",
            default=territory.name or "",
            required=False,
            max_length=255
        )
        self.add_item(self.name_input)

        # Original nation field
        self.original_nation_input = discord.ui.TextInput(
            label="Original Nation",
            placeholder="e.g., 'fire-nation'",
            default=territory.original_nation or "",
            required=False,
            max_length=50
        )
        self.add_item(self.original_nation_input)

        # Production fields (as comma-separated values)
        production_str = f"{territory.ore_production},{territory.lumber_production},{territory.coal_production},{territory.rations_production},{territory.cloth_production},{territory.platinum_production}"
        self.production_input = discord.ui.TextInput(
            label="Production (ore,lum,coal,rat,cloth,plat)",
            placeholder="e.g., 5,3,2,8,4,0",
            default=production_str,
            required=True,
            max_length=50
        )
        self.add_item(self.production_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission."""
        from helpers import emotive_message
        import asyncpg

        # Parse production values
        try:
            production_parts = [int(x.strip()) for x in self.production_input.value.split(',')]
            if len(production_parts) != 6:
                await interaction.response.send_message(
                    emotive_message("Production must have exactly 6 values (ore, lumber, coal, rations, cloth, platinum)."),
                    ephemeral=True
                )
                return

            ore, lumber, coal, rations, cloth, platinum = production_parts

            if any(x < 0 for x in production_parts):
                await interaction.response.send_message(
                    emotive_message("Production values cannot be negative."),
                    ephemeral=True
                )
                return

        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid production values. Use integers separated by commas."),
                ephemeral=True
            )
            return

        # Update territory
        self.territory.name = self.name_input.value if self.name_input.value else None
        self.territory.original_nation = self.original_nation_input.value if self.original_nation_input.value else None
        self.territory.ore_production = ore
        self.territory.lumber_production = lumber
        self.territory.coal_production = coal
        self.territory.rations_production = rations
        self.territory.cloth_production = cloth
        self.territory.platinum_production = platinum

        # Save to database
        async with self.db_pool.acquire() as conn:
            await self.territory.upsert(conn)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited territory {self.territory.territory_id} via modal in guild {interaction.guild_id}")

        await interaction.response.send_message(
            emotive_message(f"Territory {self.territory.territory_id} updated successfully."),
            ephemeral=False
        )


class EditUnitTypeModal(discord.ui.Modal, title="Edit Unit Type"):
    """Modal for editing unit type properties."""

    def __init__(self, unit_type: Optional[UnitType] = None, type_id: str = None, name: str = None, db_pool = None):
        super().__init__()
        self.unit_type = unit_type
        self.type_id = type_id
        self.name_value = name
        self.db_pool = db_pool

        # Nation field (optional)
        if unit_type:
            nation_str = unit_type.nation or ""
        else:
            nation_str = ""

        self.nation_input = discord.ui.TextInput(
            label="Nation (leave empty for any nation)",
            placeholder="e.g., fire_nation",
            default=nation_str,
            required=False,
            max_length=50
        )
        self.add_item(self.nation_input)

        # Stats field (movement,org,atk,def,siege_atk,siege_def,size,capacity)
        if unit_type:
            stats_str = f"{unit_type.movement},{unit_type.organization},{unit_type.attack},{unit_type.defense},{unit_type.siege_attack},{unit_type.siege_defense},{unit_type.size},{unit_type.capacity}"
        else:
            stats_str = "2,10,5,5,2,3,1,0"

        self.stats_input = discord.ui.TextInput(
            label="Stats (move,org,atk,def,s_atk,s_def,size,cap)",
            placeholder="e.g., 2,10,5,5,2,3,1,0",
            default=stats_str,
            required=True,
            max_length=100
        )
        self.add_item(self.stats_input)

        # Cost field (ore,lumber,coal,rations,cloth,platinum)
        if unit_type:
            cost_str = f"{unit_type.cost_ore},{unit_type.cost_lumber},{unit_type.cost_coal},{unit_type.cost_rations},{unit_type.cost_cloth},{unit_type.cost_platinum}"
        else:
            cost_str = "5,2,0,10,5,0"

        self.cost_input = discord.ui.TextInput(
            label="Cost (ore,lum,coal,rat,cloth,plat)",
            placeholder="e.g., 5,2,0,10,5,0",
            default=cost_str,
            required=True,
            max_length=50
        )
        self.add_item(self.cost_input)

        # Upkeep field (ore,lumber,coal,rations,cloth,platinum)
        if unit_type:
            upkeep_str = f"{unit_type.upkeep_ore},{unit_type.upkeep_lumber},{unit_type.upkeep_coal},{unit_type.upkeep_rations},{unit_type.upkeep_cloth},{unit_type.upkeep_platinum}"
        else:
            upkeep_str = "0,0,0,2,1,0"

        self.upkeep_input = discord.ui.TextInput(
            label="Upkeep (ore,lum,coal,rat,cloth,plat)",
            placeholder="e.g., 0,0,0,2,1,0",
            default=upkeep_str,
            required=True,
            max_length=50
        )
        self.add_item(self.upkeep_input)

        # Naval flag
        if unit_type:
            naval_str = "yes" if unit_type.is_naval else "no"
        else:
            naval_str = "no"

        self.naval_input = discord.ui.TextInput(
            label="Naval unit? (yes/no)",
            placeholder="yes or no",
            default=naval_str,
            required=True,
            max_length=3
        )
        self.add_item(self.naval_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission."""
        from helpers import emotive_message

        # Parse stats
        try:
            stats_parts = [int(x.strip()) for x in self.stats_input.value.split(',')]
            if len(stats_parts) != 8:
                await interaction.response.send_message(
                    emotive_message("Stats must have exactly 8 values (movement, org, attack, defense, siege_attack, siege_defense, size, capacity)."),
                    ephemeral=True
                )
                return

            movement, organization, attack, defense, siege_attack, siege_defense, size, capacity = stats_parts

            if any(x < 0 for x in stats_parts):
                await interaction.response.send_message(
                    emotive_message("Stats cannot be negative."),
                    ephemeral=True
                )
                return

        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid stats values. Use integers separated by commas."),
                ephemeral=True
            )
            return

        # Parse cost
        try:
            cost_parts = [int(x.strip()) for x in self.cost_input.value.split(',')]
            if len(cost_parts) != 6:
                await interaction.response.send_message(
                    emotive_message("Cost must have exactly 6 values (ore, lumber, coal, rations, cloth, platinum)."),
                    ephemeral=True
                )
                return

            cost_ore, cost_lumber, cost_coal, cost_rations, cost_cloth, cost_platinum = cost_parts

            if any(x < 0 for x in cost_parts):
                await interaction.response.send_message(
                    emotive_message("Cost values cannot be negative."),
                    ephemeral=True
                )
                return

        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid cost values. Use integers separated by commas."),
                ephemeral=True
            )
            return

        # Parse upkeep
        try:
            upkeep_parts = [int(x.strip()) for x in self.upkeep_input.value.split(',')]
            if len(upkeep_parts) != 6:
                await interaction.response.send_message(
                    emotive_message("Upkeep must have exactly 6 values (ore, lumber, coal, rations, cloth, platinum)."),
                    ephemeral=True
                )
                return

            upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth, upkeep_platinum = upkeep_parts

            if any(x < 0 for x in upkeep_parts):
                await interaction.response.send_message(
                    emotive_message("Upkeep values cannot be negative."),
                    ephemeral=True
                )
                return

        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid upkeep values. Use integers separated by commas."),
                ephemeral=True
            )
            return

        # Parse naval flag
        naval_str = self.naval_input.value.strip().lower()
        if naval_str not in ['yes', 'no']:
            await interaction.response.send_message(
                emotive_message("Naval flag must be 'yes' or 'no'."),
                ephemeral=True
            )
            return
        is_naval = naval_str == 'yes'

        # Get nation from input (empty string becomes None)
        nation = self.nation_input.value.strip() if self.nation_input.value.strip() else None

        # Update or create unit type
        if self.unit_type:
            # Update existing
            self.unit_type.nation = nation
            self.unit_type.movement = movement
            self.unit_type.organization = organization
            self.unit_type.attack = attack
            self.unit_type.defense = defense
            self.unit_type.siege_attack = siege_attack
            self.unit_type.siege_defense = siege_defense
            self.unit_type.size = size
            self.unit_type.capacity = capacity
            self.unit_type.cost_ore = cost_ore
            self.unit_type.cost_lumber = cost_lumber
            self.unit_type.cost_coal = cost_coal
            self.unit_type.cost_rations = cost_rations
            self.unit_type.cost_cloth = cost_cloth
            self.unit_type.cost_platinum = cost_platinum
            self.unit_type.upkeep_ore = upkeep_ore
            self.unit_type.upkeep_lumber = upkeep_lumber
            self.unit_type.upkeep_coal = upkeep_coal
            self.unit_type.upkeep_rations = upkeep_rations
            self.unit_type.upkeep_cloth = upkeep_cloth
            self.unit_type.upkeep_platinum = upkeep_platinum
            self.unit_type.is_naval = is_naval

            # Save to database
            async with self.db_pool.acquire() as conn:
                await self.unit_type.upsert(conn)

            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit type '{self.unit_type.type_id}' (nation: {nation}) via modal in guild {interaction.guild_id}")

            await interaction.response.send_message(
                emotive_message(f"Unit type '{self.unit_type.name}' updated successfully."),
                ephemeral=False
            )
        else:
            # Create new
            unit_type = UnitType(
                type_id=self.type_id,
                name=self.name_value,
                nation=nation,
                movement=movement,
                organization=organization,
                attack=attack,
                defense=defense,
                siege_attack=siege_attack,
                siege_defense=siege_defense,
                size=size,
                capacity=capacity,
                cost_ore=cost_ore,
                cost_lumber=cost_lumber,
                cost_coal=cost_coal,
                cost_rations=cost_rations,
                cost_cloth=cost_cloth,
                cost_platinum=cost_platinum,
                upkeep_ore=upkeep_ore,
                upkeep_lumber=upkeep_lumber,
                upkeep_coal=upkeep_coal,
                upkeep_rations=upkeep_rations,
                upkeep_cloth=upkeep_cloth,
                upkeep_platinum=upkeep_platinum,
                is_naval=is_naval,
                keywords=[],
                guild_id=interaction.guild_id
            )

            # Save to database
            async with self.db_pool.acquire() as conn:
                await unit_type.upsert(conn)

            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) created unit type '{self.type_id}' (name: {self.name_value}, nation: {nation}) via modal in guild {interaction.guild_id}")

            await interaction.response.send_message(
                emotive_message(f"Unit type '{self.name_value}' created successfully."),
                ephemeral=False
            )


class EditWargameConfigModal(discord.ui.Modal, title="Edit Wargame Config"):
    """Modal for editing wargame configuration."""

    def __init__(self, config: WargameConfig, db_pool, guild):
        super().__init__()
        self.config = config
        self.db_pool = db_pool
        self.guild = guild

        # Current turn field
        self.current_turn_input = discord.ui.TextInput(
            label="Current Turn",
            placeholder="Turn number (integer)",
            default=str(config.current_turn),
            required=True,
            max_length=10
        )
        self.add_item(self.current_turn_input)

        # Turn resolution enabled field
        self.turn_resolution_enabled_input = discord.ui.TextInput(
            label="Turn Resolution Enabled (yes/no)",
            placeholder="yes or no",
            default="yes" if config.turn_resolution_enabled else "no",
            required=True,
            max_length=3
        )
        self.add_item(self.turn_resolution_enabled_input)

        # Max movement stat field
        self.max_movement_stat_input = discord.ui.TextInput(
            label="Max Movement Stat",
            placeholder="Maximum movement value (integer)",
            default=str(config.max_movement_stat),
            required=True,
            max_length=10
        )
        self.add_item(self.max_movement_stat_input)

        # GM reports channel field (channel name)
        current_channel_name = ""
        if config.gm_reports_channel_id:
            channel = guild.get_channel(config.gm_reports_channel_id)
            if channel:
                current_channel_name = channel.name

        self.gm_reports_channel_input = discord.ui.TextInput(
            label="GM Reports Channel",
            placeholder="Channel name (or leave empty for none)",
            default=current_channel_name,
            required=False,
            max_length=100
        )
        self.add_item(self.gm_reports_channel_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission."""
        from helpers import emotive_message

        # Parse current turn
        try:
            current_turn = int(self.current_turn_input.value.strip())
            if current_turn < 0:
                await interaction.response.send_message(
                    emotive_message("Current turn cannot be negative."),
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid current turn value. Use integers only."),
                ephemeral=True
            )
            return

        # Parse turn resolution enabled
        turn_res_str = self.turn_resolution_enabled_input.value.strip().lower()
        if turn_res_str not in ['yes', 'no']:
            await interaction.response.send_message(
                emotive_message("Turn resolution enabled must be 'yes' or 'no'."),
                ephemeral=True
            )
            return
        turn_resolution_enabled = turn_res_str == 'yes'

        # Parse max movement stat
        try:
            max_movement_stat = int(self.max_movement_stat_input.value.strip())
            if max_movement_stat < 0:
                await interaction.response.send_message(
                    emotive_message("Max movement stat cannot be negative."),
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid max movement stat value. Use integers only."),
                ephemeral=True
            )
            return

        # Parse GM reports channel
        gm_reports_channel_id = None
        channel_name = self.gm_reports_channel_input.value.strip()
        if channel_name:
            # Find channel by name
            found_channel = None
            for channel in self.guild.text_channels:
                if channel.name == channel_name:
                    found_channel = channel
                    break

            if not found_channel:
                await interaction.response.send_message(
                    emotive_message(f"Channel '{channel_name}' not found. Please check the channel name and try again."),
                    ephemeral=True
                )
                return

            gm_reports_channel_id = found_channel.id

        # Update config
        self.config.current_turn = current_turn
        self.config.turn_resolution_enabled = turn_resolution_enabled
        self.config.max_movement_stat = max_movement_stat
        self.config.gm_reports_channel_id = gm_reports_channel_id

        # Verify config
        is_valid, error_msg = self.config.verify()
        if not is_valid:
            await interaction.response.send_message(
                emotive_message(f"Invalid configuration: {error_msg}"),
                ephemeral=True
            )
            return

        # Save to database
        async with self.db_pool.acquire() as conn:
            await self.config.upsert(conn)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited wargame config via modal in guild {interaction.guild_id} (turn: {current_turn}, turn_res_enabled: {turn_resolution_enabled}, max_movement: {max_movement_stat}, gm_reports_channel: {gm_reports_channel_id})")

        await interaction.response.send_message(
            emotive_message("Wargame configuration updated successfully."),
            ephemeral=False
        )


class SingleResourceModal(discord.ui.Modal):
    """Modal for editing a single resource value."""

    def __init__(self, resource_name: str, resource_emoji: str, current_value: int,
                 character: Character, resources: PlayerResources, db_pool, parent_view):
        super().__init__(title=f"Modify {resource_name}")
        self.resource_name = resource_name.lower()
        self.resource_emoji = resource_emoji
        self.character = character
        self.resources = resources
        self.db_pool = db_pool
        self.parent_view = parent_view

        self.value_input = discord.ui.TextInput(
            label=f"{resource_emoji} {resource_name}",
            default=str(current_value),
            required=True,
            max_length=10
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission."""
        from helpers import emotive_message
        from embeds import create_modify_resources_embed

        try:
            new_value = int(self.value_input.value.strip())
            if new_value < 0:
                await interaction.response.send_message(
                    emotive_message("Resource values cannot be negative."),
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid value. Use integers only."),
                ephemeral=True
            )
            return

        # Update the resource
        setattr(self.resources, self.resource_name, new_value)

        # Save to database
        async with self.db_pool.acquire() as conn:
            await self.resources.upsert(conn)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) modified {self.resource_name} to {new_value} for character '{self.character.name}' in guild {interaction.guild_id}")

        # Update the embed
        new_embed = create_modify_resources_embed(self.character, self.resources)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class ModifyResourcesView(discord.ui.View):
    """View with buttons to modify individual resources."""

    RESOURCES = [
        ('ore', 'Ore', '⛏️'),
        ('lumber', 'Lumber', '🪵'),
        ('coal', 'Coal', '⚫'),
        ('rations', 'Rations', '🍖'),
        ('cloth', 'Cloth', '🧵'),
        ('platinum', 'Platinum', '🪙'),
    ]

    def __init__(self, character: Character, resources: PlayerResources, db_pool):
        super().__init__(timeout=300)  # 5 minute timeout
        self.character = character
        self.resources = resources
        self.db_pool = db_pool

        # Add resource buttons
        for attr, name, emoji in self.RESOURCES:
            button = discord.ui.Button(
                label=name,
                emoji=emoji,
                style=discord.ButtonStyle.secondary,
                custom_id=f"resource_{attr}"
            )
            button.callback = self._make_callback(attr, name, emoji)
            self.add_item(button)

    def _make_callback(self, attr: str, name: str, emoji: str):
        async def callback(interaction: discord.Interaction):
            current_value = getattr(self.resources, attr)
            modal = SingleResourceModal(
                name, emoji, current_value,
                self.character, self.resources, self.db_pool, self
            )
            await interaction.response.send_modal(modal)
        return callback


class SingleProductionModal(discord.ui.Modal):
    """Modal for editing a single production value."""

    def __init__(self, resource_name: str, resource_emoji: str, current_value: int,
                 character: Character, db_pool, parent_view):
        super().__init__(title=f"Modify {resource_name} Production")
        self.resource_name = resource_name.lower()
        self.resource_emoji = resource_emoji
        self.character = character
        self.db_pool = db_pool
        self.parent_view = parent_view

        self.value_input = discord.ui.TextInput(
            label=f"{resource_emoji} {resource_name} Production",
            default=str(current_value),
            required=True,
            max_length=10
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission."""
        from helpers import emotive_message
        from embeds import create_modify_character_production_embed

        try:
            new_value = int(self.value_input.value.strip())
            if new_value < 0:
                await interaction.response.send_message(
                    emotive_message("Production values cannot be negative."),
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid value. Use integers only."),
                ephemeral=True
            )
            return

        # Update the character's production field
        setattr(self.character, f"{self.resource_name}_production", new_value)

        # Save to database
        async with self.db_pool.acquire() as conn:
            await self.character.upsert(conn)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) modified {self.resource_name}_production to {new_value} for character '{self.character.name}' in guild {interaction.guild_id}")

        # Update the embed
        new_embed = create_modify_character_production_embed(self.character)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class ModifyCharacterProductionView(discord.ui.View):
    """View with buttons to modify individual character production values."""

    RESOURCES = [
        ('ore', 'Ore', '⛏️'),
        ('lumber', 'Lumber', '🪵'),
        ('coal', 'Coal', '⚫'),
        ('rations', 'Rations', '🍖'),
        ('cloth', 'Cloth', '🧵'),
        ('platinum', 'Platinum', '🪙'),
    ]

    def __init__(self, character: Character, db_pool):
        super().__init__(timeout=300)  # 5 minute timeout
        self.character = character
        self.db_pool = db_pool

        # Add resource buttons
        for attr, name, emoji in self.RESOURCES:
            button = discord.ui.Button(
                label=name,
                emoji=emoji,
                style=discord.ButtonStyle.secondary,
                custom_id=f"production_{attr}"
            )
            button.callback = self._make_callback(attr, name, emoji)
            self.add_item(button)

    def _make_callback(self, attr: str, name: str, emoji: str):
        async def callback(interaction: discord.Interaction):
            current_value = getattr(self.character, f"{attr}_production")
            modal = SingleProductionModal(
                name, emoji, current_value,
                self.character, self.db_pool, self
            )
            await interaction.response.send_modal(modal)
        return callback


class ModifyCharacterVPModal(discord.ui.Modal, title="Modify Victory Points"):
    """Modal for editing character victory points."""

    def __init__(self, character: Character, db_pool):
        super().__init__()
        self.character = character
        self.db_pool = db_pool

        self.vp_input = discord.ui.TextInput(
            label="Victory Points",
            default=str(character.victory_points),
            required=True,
            max_length=10
        )
        self.add_item(self.vp_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission."""
        from helpers import emotive_message

        try:
            new_value = int(self.vp_input.value.strip())
            if new_value < 0:
                await interaction.response.send_message(
                    emotive_message("Victory points cannot be negative."),
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid value. Use integers only."),
                ephemeral=True
            )
            return

        self.character.victory_points = new_value

        async with self.db_pool.acquire() as conn:
            await self.character.upsert(conn)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) modified victory_points to {new_value} for character '{self.character.name}' in guild {interaction.guild_id}")

        await interaction.response.send_message(
            emotive_message(f"Victory points for {self.character.name} set to {new_value}."),
            ephemeral=False
        )


class AssignCommanderConfirmView(discord.ui.View):
    """Confirmation view for assigning a commander from a different faction."""

    def __init__(
        self,
        unit_id: str,
        new_commander_identifier: str,
        new_commander_name: str,
        warning_message: str,
        db_pool,
        guild_id: int,
        submitting_character_id: int
    ):
        super().__init__(timeout=60)  # 60 second timeout
        self.unit_id = unit_id
        self.new_commander_identifier = new_commander_identifier
        self.new_commander_name = new_commander_name
        self.warning_message = warning_message
        self.db_pool = db_pool
        self.guild_id = guild_id
        self.submitting_character_id = submitting_character_id

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle confirmation - proceed with the order."""
        from helpers import emotive_message
        from handlers.order_handlers import submit_assign_commander_order

        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        # Submit the order with confirmed=True
        async with self.db_pool.acquire() as conn:
            success, message, _ = await submit_assign_commander_order(
                conn,
                self.unit_id,
                self.new_commander_identifier,
                self.guild_id,
                self.submitting_character_id,
                confirmed=True
            )

        if success:
            await interaction.followup.send(emotive_message(message), ephemeral=False)
        else:
            await interaction.followup.send(emotive_message(message), ephemeral=True)

        logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) confirmed commander assignment: {self.unit_id} -> {self.new_commander_name} in guild {self.guild_id}")

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle cancellation - do not proceed."""
        from helpers import emotive_message

        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)

        await interaction.followup.send(emotive_message("Commander assignment cancelled."), ephemeral=True)

        logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) cancelled commander assignment: {self.unit_id} -> {self.new_commander_name} in guild {self.guild_id}")
