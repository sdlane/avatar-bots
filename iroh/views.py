"""
Discord UI components (modals, views, buttons) for Iroh wargame bot.
"""
import discord
from typing import Optional
from db import Territory, UnitType, BuildingType, PlayerResources, Character, WargameConfig, Unit, Faction, FactionMember, NavalUnitPosition
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

        # Keywords field
        self.keywords_input = discord.ui.TextInput(
            label="Keywords (comma-separated)",
            placeholder="e.g., capital, fortified, contested",
            default=", ".join(territory.keywords) if territory.keywords else "",
            required=False,
            max_length=500
        )
        self.add_item(self.keywords_input)

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

        # Parse keywords
        keywords_str = self.keywords_input.value.strip()
        if keywords_str:
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        else:
            keywords = []

        # Update territory
        self.territory.name = self.name_input.value if self.name_input.value else None
        self.territory.original_nation = self.original_nation_input.value if self.original_nation_input.value else None
        self.territory.ore_production = ore
        self.territory.lumber_production = lumber
        self.territory.coal_production = coal
        self.territory.rations_production = rations
        self.territory.cloth_production = cloth
        self.territory.platinum_production = platinum
        self.territory.keywords = keywords

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


class EditBuildingTypeModal(discord.ui.Modal, title="Edit Building Type"):
    """Modal for editing building type properties."""

    def __init__(self, building_type: Optional[BuildingType] = None, type_id: str = None, name: str = None, db_pool = None):
        super().__init__()
        self.building_type = building_type
        self.type_id = type_id
        self.name_value = name
        self.db_pool = db_pool

        # Description field (optional)
        self.description_input = discord.ui.TextInput(
            label="Description (optional)",
            placeholder="A brief description of the building",
            default=building_type.description or "" if building_type else "",
            required=False,
            max_length=500,
            style=discord.TextStyle.paragraph
        )
        self.add_item(self.description_input)

        # Cost field (ore,lumber,coal,rations,cloth,platinum)
        if building_type:
            cost_str = f"{building_type.cost_ore},{building_type.cost_lumber},{building_type.cost_coal},{building_type.cost_rations},{building_type.cost_cloth},{building_type.cost_platinum}"
        else:
            cost_str = "10,10,0,0,0,0"

        self.cost_input = discord.ui.TextInput(
            label="Cost (ore,lum,coal,rat,cloth,plat)",
            placeholder="e.g., 10,10,0,0,0,0",
            default=cost_str,
            required=True,
            max_length=50
        )
        self.add_item(self.cost_input)

        # Upkeep field (ore,lumber,coal,rations,cloth,platinum)
        if building_type:
            upkeep_str = f"{building_type.upkeep_ore},{building_type.upkeep_lumber},{building_type.upkeep_coal},{building_type.upkeep_rations},{building_type.upkeep_cloth},{building_type.upkeep_platinum}"
        else:
            upkeep_str = "0,1,0,0,0,0"

        self.upkeep_input = discord.ui.TextInput(
            label="Upkeep (ore,lum,coal,rat,cloth,plat)",
            placeholder="e.g., 0,1,0,0,0,0",
            default=upkeep_str,
            required=True,
            max_length=50
        )
        self.add_item(self.upkeep_input)

        # Keywords field
        if building_type:
            keywords_str = ", ".join(building_type.keywords) if building_type.keywords else ""
        else:
            keywords_str = ""

        self.keywords_input = discord.ui.TextInput(
            label="Keywords (comma-separated)",
            placeholder="e.g., fortification, production, military",
            default=keywords_str,
            required=False,
            max_length=500
        )
        self.add_item(self.keywords_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission."""
        from helpers import emotive_message

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

        # Get description from input (empty string becomes None)
        description = self.description_input.value.strip() if self.description_input.value.strip() else None

        # Parse keywords
        keywords_str = self.keywords_input.value.strip()
        if keywords_str:
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        else:
            keywords = []

        # Update or create building type
        if self.building_type:
            # Update existing
            self.building_type.description = description
            self.building_type.cost_ore = cost_ore
            self.building_type.cost_lumber = cost_lumber
            self.building_type.cost_coal = cost_coal
            self.building_type.cost_rations = cost_rations
            self.building_type.cost_cloth = cost_cloth
            self.building_type.cost_platinum = cost_platinum
            self.building_type.upkeep_ore = upkeep_ore
            self.building_type.upkeep_lumber = upkeep_lumber
            self.building_type.upkeep_coal = upkeep_coal
            self.building_type.upkeep_rations = upkeep_rations
            self.building_type.upkeep_cloth = upkeep_cloth
            self.building_type.upkeep_platinum = upkeep_platinum
            self.building_type.keywords = keywords

            # Save to database
            async with self.db_pool.acquire() as conn:
                await self.building_type.upsert(conn)

            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited building type '{self.building_type.type_id}' via modal in guild {interaction.guild_id}")

            await interaction.response.send_message(
                emotive_message(f"Building type '{self.building_type.name}' updated successfully."),
                ephemeral=False
            )
        else:
            # Create new
            building_type = BuildingType(
                type_id=self.type_id,
                name=self.name_value,
                description=description,
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
                keywords=keywords,
                guild_id=interaction.guild_id
            )

            # Save to database
            async with self.db_pool.acquire() as conn:
                await building_type.upsert(conn)

            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) created building type '{self.type_id}' (name: {self.name_value}) via modal in guild {interaction.guild_id}")

            await interaction.response.send_message(
                emotive_message(f"Building type '{self.name_value}' created successfully."),
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


class UnitOrderConfirmView(discord.ui.View):
    """Confirmation view for overriding existing unit orders."""

    def __init__(
        self,
        unit_ids: list,
        action: str,
        path: list,
        speed: int | None,
        existing_orders: list,
        db_pool,
        guild_id: int,
        submitting_character_id: int
    ):
        super().__init__(timeout=60)  # 60 second timeout
        self.unit_ids = unit_ids
        self.action = action
        self.path = path
        self.speed = speed
        self.existing_orders = existing_orders
        self.db_pool = db_pool
        self.guild_id = guild_id
        self.submitting_character_id = submitting_character_id

    @discord.ui.button(label="Confirm Override", style=discord.ButtonStyle.danger)
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle confirmation - cancel old orders and create new one."""
        from helpers import emotive_message
        from handlers.order_handlers import submit_unit_order

        # Submit the order with override=True
        async with self.db_pool.acquire() as conn:
            success, message, _ = await submit_unit_order(
                conn,
                self.unit_ids,
                self.action,
                self.path,
                self.guild_id,
                self.submitting_character_id,
                speed=self.speed,
                override=True
            )

        # Replace the confirmation message with the result
        await interaction.response.edit_message(content=emotive_message(message), view=None)

        logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) confirmed unit order override: {self.action} for {self.unit_ids} in guild {self.guild_id}")

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Handle cancellation - do not proceed."""
        from helpers import emotive_message

        # Replace the confirmation message with cancellation notice
        await interaction.response.edit_message(content=emotive_message("Unit order cancelled."), view=None)

        logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) cancelled unit order: {self.action} for {self.unit_ids} in guild {self.guild_id}")


# ============== Edit Unit Components ==============


class EditUnitBasicModal(discord.ui.Modal, title="Edit Basic Info"):
    """Modal for editing unit basic info."""

    def __init__(self, unit: Unit, db_pool, parent_view):
        super().__init__()
        self.unit = unit
        self.db_pool = db_pool
        self.parent_view = parent_view

        self.unit_id_input = discord.ui.TextInput(
            label="Unit ID",
            default=unit.unit_id,
            required=True,
            max_length=100
        )
        self.name_input = discord.ui.TextInput(
            label="Name (leave empty to clear)",
            default=unit.name or "",
            required=False,
            max_length=255
        )
        self.type_input = discord.ui.TextInput(
            label="Unit Type",
            default=unit.unit_type,
            required=True,
            max_length=100
        )
        self.status_input = discord.ui.TextInput(
            label="Status (ACTIVE or DISBANDED)",
            default=unit.status,
            required=True,
            max_length=10
        )

        self.add_item(self.unit_id_input)
        self.add_item(self.name_input)
        self.add_item(self.type_input)
        self.add_item(self.status_input)

    async def on_submit(self, interaction: discord.Interaction):
        from helpers import emotive_message
        from embeds import create_edit_unit_embed

        new_unit_id = self.unit_id_input.value.strip()
        new_name = self.name_input.value.strip() or None
        new_type = self.type_input.value.strip()
        new_status = self.status_input.value.strip().upper()

        # Validate status
        if new_status not in ['ACTIVE', 'DISBANDED']:
            await interaction.response.send_message(
                emotive_message("Status must be 'ACTIVE' or 'DISBANDED'."),
                ephemeral=True
            )
            return

        async with self.db_pool.acquire() as conn:
            # Validate unit type exists
            unit_type_obj = await UnitType.fetch_by_type_id(conn, new_type, interaction.guild_id)
            if not unit_type_obj:
                await interaction.response.send_message(
                    emotive_message(f"Unit type '{new_type}' not found."),
                    ephemeral=True
                )
                return

            # Check if renaming and new ID already exists
            if new_unit_id != self.unit.unit_id:
                existing = await Unit.fetch_by_unit_id(conn, new_unit_id, interaction.guild_id)
                if existing:
                    await interaction.response.send_message(
                        emotive_message(f"Unit ID '{new_unit_id}' already exists."),
                        ephemeral=True
                    )
                    return
                # Delete old unit and create with new ID
                await Unit.delete(conn, self.unit.unit_id, interaction.guild_id)
                self.unit.unit_id = new_unit_id

            self.unit.name = new_name
            self.unit.unit_type = new_type
            self.unit.status = new_status
            await self.unit.upsert(conn)

        # Update parent view's unit reference
        self.parent_view.unit = self.unit

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit basic info for '{self.unit.unit_id}' in guild {interaction.guild_id}")

        new_embed = create_edit_unit_embed(self.unit, naval_positions=self.parent_view.naval_positions)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class EditUnitLocationModal(discord.ui.Modal, title="Edit Location"):
    """Modal for editing unit location."""

    def __init__(self, unit: Unit, db_pool, parent_view, naval_positions_str: str = ""):
        super().__init__()
        self.unit = unit
        self.db_pool = db_pool
        self.parent_view = parent_view

        self.territory_input = discord.ui.TextInput(
            label="Territory ID (leave empty to clear)",
            default=unit.current_territory_id or "",
            required=False,
            max_length=100
        )
        self.add_item(self.territory_input)

        self.naval_positions_input = None
        if unit.is_naval:
            self.naval_positions_input = discord.ui.TextInput(
                label="Naval Positions (comma-separated)",
                style=discord.TextStyle.long,
                default=naval_positions_str,
                placeholder="e.g. ocean-1, ocean-2, ocean-3",
                required=False,
                max_length=1000
            )
            self.add_item(self.naval_positions_input)

    async def on_submit(self, interaction: discord.Interaction):
        from helpers import emotive_message
        from embeds import create_edit_unit_embed
        from db import Territory

        territory_id = self.territory_input.value.strip() or None

        async with self.db_pool.acquire() as conn:
            # Validate territory exists if specified
            if territory_id:
                territory = await Territory.fetch_by_territory_id(conn, territory_id, interaction.guild_id)
                if not territory:
                    await interaction.response.send_message(
                        emotive_message(f"Territory '{territory_id}' not found."),
                        ephemeral=True
                    )
                    return

            self.unit.current_territory_id = territory_id
            await self.unit.upsert(conn)

            # Handle naval positions if this is a naval unit
            if self.unit.is_naval and self.naval_positions_input is not None:
                raw = self.naval_positions_input.value.strip()
                if raw:
                    # Parse, deduplicate while preserving order
                    seen = set()
                    parsed_ids = []
                    for tid in raw.split(","):
                        tid = tid.strip()
                        if tid and tid not in seen:
                            seen.add(tid)
                            parsed_ids.append(tid)

                    # Validate each territory exists
                    for tid in parsed_ids:
                        t = await Territory.fetch_by_territory_id(conn, tid, interaction.guild_id)
                        if not t:
                            await interaction.response.send_message(
                                emotive_message(f"Naval position territory '{tid}' not found."),
                                ephemeral=True
                            )
                            return

                    await NavalUnitPosition.set_positions(conn, self.unit.id, parsed_ids, interaction.guild_id)
                    self.parent_view.naval_positions = parsed_ids
                else:
                    # Empty input clears all naval positions
                    await NavalUnitPosition.set_positions(conn, self.unit.id, [], interaction.guild_id)
                    self.parent_view.naval_positions = []

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit location for '{self.unit.unit_id}' to '{territory_id}' in guild {interaction.guild_id}")

        new_embed = create_edit_unit_embed(self.unit, naval_positions=self.parent_view.naval_positions)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class EditUnitOwnershipModal(discord.ui.Modal, title="Edit Ownership"):
    """Modal for editing unit ownership."""

    def __init__(self, unit: Unit, db_pool, parent_view, owner_char_identifier: str, owner_faction_id: str, faction_id: str):
        super().__init__()
        self.unit = unit
        self.db_pool = db_pool
        self.parent_view = parent_view

        self.owner_char_input = discord.ui.TextInput(
            label="Owner Character (identifier)",
            default=owner_char_identifier,
            required=False,
            max_length=100
        )
        self.owner_faction_input = discord.ui.TextInput(
            label="Owner Faction (faction_id)",
            default=owner_faction_id,
            required=False,
            max_length=100
        )
        self.faction_input = discord.ui.TextInput(
            label="Faction (faction_id)",
            default=faction_id,
            required=False,
            max_length=100
        )

        self.add_item(self.owner_char_input)
        self.add_item(self.owner_faction_input)
        self.add_item(self.faction_input)

    async def on_submit(self, interaction: discord.Interaction):
        from helpers import emotive_message
        from embeds import create_edit_unit_embed

        owner_char = self.owner_char_input.value.strip() or None
        owner_faction = self.owner_faction_input.value.strip() or None
        faction = self.faction_input.value.strip() or None

        # Validate cannot set both owner_character and owner_faction
        if owner_char and owner_faction:
            await interaction.response.send_message(
                emotive_message("Cannot set both owner_character and owner_faction. Choose one."),
                ephemeral=True
            )
            return

        async with self.db_pool.acquire() as conn:
            # Validate owner character if specified
            owner_char_id = None
            if owner_char:
                char = await Character.fetch_by_identifier(conn, owner_char, interaction.guild_id)
                if not char:
                    await interaction.response.send_message(
                        emotive_message(f"Character '{owner_char}' not found."),
                        ephemeral=True
                    )
                    return
                owner_char_id = char.id

            # Validate owner faction if specified
            owner_faction_id = None
            if owner_faction:
                fact = await Faction.fetch_by_faction_id(conn, owner_faction, interaction.guild_id)
                if not fact:
                    await interaction.response.send_message(
                        emotive_message(f"Faction '{owner_faction}' not found."),
                        ephemeral=True
                    )
                    return
                owner_faction_id = fact.id

            # Validate faction if specified
            faction_id = None
            if faction:
                fact = await Faction.fetch_by_faction_id(conn, faction, interaction.guild_id)
                if not fact:
                    await interaction.response.send_message(
                        emotive_message(f"Faction '{faction}' not found."),
                        ephemeral=True
                    )
                    return
                faction_id = fact.id

            self.unit.owner_character_id = owner_char_id
            self.unit.owner_faction_id = owner_faction_id
            self.unit.faction_id = faction_id
            await self.unit.upsert(conn)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit ownership for '{self.unit.unit_id}' in guild {interaction.guild_id}")

        new_embed = create_edit_unit_embed(self.unit, naval_positions=self.parent_view.naval_positions)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class EditUnitCommanderModal(discord.ui.Modal, title="Edit Commander"):
    """Modal for editing unit commander."""

    def __init__(self, unit: Unit, db_pool, parent_view, commander_identifier: str):
        super().__init__()
        self.unit = unit
        self.db_pool = db_pool
        self.parent_view = parent_view

        self.commander_input = discord.ui.TextInput(
            label="Commander (identifier, 'none' to clear)",
            default=commander_identifier,
            required=False,
            max_length=100
        )
        self.add_item(self.commander_input)

    async def on_submit(self, interaction: discord.Interaction):
        from helpers import emotive_message
        from embeds import create_edit_unit_embed

        commander = self.commander_input.value.strip()

        async with self.db_pool.acquire() as conn:
            # Handle clearing commander
            if not commander or commander.lower() == 'none':
                self.unit.commander_character_id = None
                self.unit.commander_assigned_turn = None
            else:
                # Validate commander character exists
                char = await Character.fetch_by_identifier(conn, commander, interaction.guild_id)
                if not char:
                    await interaction.response.send_message(
                        emotive_message(f"Character '{commander}' not found."),
                        ephemeral=True
                    )
                    return

                # Get current turn for commander_assigned_turn
                wargame_config = await conn.fetchrow(
                    "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
                    interaction.guild_id
                )
                current_turn = wargame_config['current_turn'] if wargame_config else 0

                self.unit.commander_character_id = char.id
                self.unit.commander_assigned_turn = current_turn

            await self.unit.upsert(conn)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit commander for '{self.unit.unit_id}' in guild {interaction.guild_id}")

        new_embed = create_edit_unit_embed(self.unit, naval_positions=self.parent_view.naval_positions)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class EditUnitCombatModal(discord.ui.Modal, title="Edit Combat Stats"):
    """Modal for editing unit combat stats."""

    def __init__(self, unit: Unit, db_pool, parent_view):
        super().__init__()
        self.unit = unit
        self.db_pool = db_pool
        self.parent_view = parent_view

        self.movement_input = discord.ui.TextInput(
            label="Movement",
            default=str(unit.movement),
            required=True,
            max_length=10
        )
        self.org_input = discord.ui.TextInput(
            label="Organization",
            default=str(unit.organization),
            required=True,
            max_length=10
        )
        self.max_org_input = discord.ui.TextInput(
            label="Max Organization",
            default=str(unit.max_organization),
            required=True,
            max_length=10
        )
        self.attack_input = discord.ui.TextInput(
            label="Attack",
            default=str(unit.attack),
            required=True,
            max_length=10
        )
        self.defense_input = discord.ui.TextInput(
            label="Defense",
            default=str(unit.defense),
            required=True,
            max_length=10
        )

        self.add_item(self.movement_input)
        self.add_item(self.org_input)
        self.add_item(self.max_org_input)
        self.add_item(self.attack_input)
        self.add_item(self.defense_input)

    async def on_submit(self, interaction: discord.Interaction):
        from helpers import emotive_message
        from embeds import create_edit_unit_embed

        try:
            movement = int(self.movement_input.value.strip())
            organization = int(self.org_input.value.strip())
            max_organization = int(self.max_org_input.value.strip())
            attack = int(self.attack_input.value.strip())
            defense = int(self.defense_input.value.strip())

            if any(v < 0 for v in [movement, organization, max_organization, attack, defense]):
                await interaction.response.send_message(
                    emotive_message("All values must be >= 0."),
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid values. All fields must be integers."),
                ephemeral=True
            )
            return

        async with self.db_pool.acquire() as conn:
            self.unit.movement = movement
            self.unit.organization = organization
            self.unit.max_organization = max_organization
            self.unit.attack = attack
            self.unit.defense = defense
            await self.unit.upsert(conn)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit combat stats for '{self.unit.unit_id}' in guild {interaction.guild_id}")

        new_embed = create_edit_unit_embed(self.unit, naval_positions=self.parent_view.naval_positions)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class EditUnitSizeModal(discord.ui.Modal, title="Edit Size/Siege Stats"):
    """Modal for editing unit size and siege stats."""

    def __init__(self, unit: Unit, db_pool, parent_view):
        super().__init__()
        self.unit = unit
        self.db_pool = db_pool
        self.parent_view = parent_view

        self.siege_attack_input = discord.ui.TextInput(
            label="Siege Attack",
            default=str(unit.siege_attack),
            required=True,
            max_length=10
        )
        self.siege_defense_input = discord.ui.TextInput(
            label="Siege Defense",
            default=str(unit.siege_defense),
            required=True,
            max_length=10
        )
        self.size_input = discord.ui.TextInput(
            label="Size",
            default=str(unit.size),
            required=True,
            max_length=10
        )
        self.capacity_input = discord.ui.TextInput(
            label="Capacity",
            default=str(unit.capacity),
            required=True,
            max_length=10
        )
        self.naval_input = discord.ui.TextInput(
            label="Is Naval (true/false)",
            default="true" if unit.is_naval else "false",
            required=True,
            max_length=5
        )

        self.add_item(self.siege_attack_input)
        self.add_item(self.siege_defense_input)
        self.add_item(self.size_input)
        self.add_item(self.capacity_input)
        self.add_item(self.naval_input)

    async def on_submit(self, interaction: discord.Interaction):
        from helpers import emotive_message
        from embeds import create_edit_unit_embed

        try:
            siege_attack = int(self.siege_attack_input.value.strip())
            siege_defense = int(self.siege_defense_input.value.strip())
            size = int(self.size_input.value.strip())
            capacity = int(self.capacity_input.value.strip())

            if any(v < 0 for v in [siege_attack, siege_defense, size, capacity]):
                await interaction.response.send_message(
                    emotive_message("All numeric values must be >= 0."),
                    ephemeral=True
                )
                return

            naval_str = self.naval_input.value.strip().lower()
            if naval_str not in ['true', 'false']:
                await interaction.response.send_message(
                    emotive_message("Is Naval must be 'true' or 'false'."),
                    ephemeral=True
                )
                return
            is_naval = naval_str == 'true'

        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid values. Numeric fields must be integers."),
                ephemeral=True
            )
            return

        async with self.db_pool.acquire() as conn:
            self.unit.siege_attack = siege_attack
            self.unit.siege_defense = siege_defense
            self.unit.size = size
            self.unit.capacity = capacity
            self.unit.is_naval = is_naval
            await self.unit.upsert(conn)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit size/siege stats for '{self.unit.unit_id}' in guild {interaction.guild_id}")

        new_embed = create_edit_unit_embed(self.unit, naval_positions=self.parent_view.naval_positions)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class EditUnitUpkeep1Modal(discord.ui.Modal, title="Edit Upkeep (1/2)"):
    """Modal for editing unit upkeep (ore, lumber, coal)."""

    def __init__(self, unit: Unit, db_pool, parent_view):
        super().__init__()
        self.unit = unit
        self.db_pool = db_pool
        self.parent_view = parent_view

        self.ore_input = discord.ui.TextInput(
            label="Ore Upkeep",
            default=str(unit.upkeep_ore),
            required=True,
            max_length=10
        )
        self.lumber_input = discord.ui.TextInput(
            label="Lumber Upkeep",
            default=str(unit.upkeep_lumber),
            required=True,
            max_length=10
        )
        self.coal_input = discord.ui.TextInput(
            label="Coal Upkeep",
            default=str(unit.upkeep_coal),
            required=True,
            max_length=10
        )

        self.add_item(self.ore_input)
        self.add_item(self.lumber_input)
        self.add_item(self.coal_input)

    async def on_submit(self, interaction: discord.Interaction):
        from helpers import emotive_message
        from embeds import create_edit_unit_embed

        try:
            ore = int(self.ore_input.value.strip())
            lumber = int(self.lumber_input.value.strip())
            coal = int(self.coal_input.value.strip())

            if any(v < 0 for v in [ore, lumber, coal]):
                await interaction.response.send_message(
                    emotive_message("All values must be >= 0."),
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid values. All fields must be integers."),
                ephemeral=True
            )
            return

        async with self.db_pool.acquire() as conn:
            self.unit.upkeep_ore = ore
            self.unit.upkeep_lumber = lumber
            self.unit.upkeep_coal = coal
            await self.unit.upsert(conn)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit upkeep (ore/lumber/coal) for '{self.unit.unit_id}' in guild {interaction.guild_id}")

        new_embed = create_edit_unit_embed(self.unit, naval_positions=self.parent_view.naval_positions)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class EditUnitUpkeep2Modal(discord.ui.Modal, title="Edit Upkeep (2/2)"):
    """Modal for editing unit upkeep (rations, cloth, platinum)."""

    def __init__(self, unit: Unit, db_pool, parent_view):
        super().__init__()
        self.unit = unit
        self.db_pool = db_pool
        self.parent_view = parent_view

        self.rations_input = discord.ui.TextInput(
            label="Rations Upkeep",
            default=str(unit.upkeep_rations),
            required=True,
            max_length=10
        )
        self.cloth_input = discord.ui.TextInput(
            label="Cloth Upkeep",
            default=str(unit.upkeep_cloth),
            required=True,
            max_length=10
        )
        self.platinum_input = discord.ui.TextInput(
            label="Platinum Upkeep",
            default=str(unit.upkeep_platinum),
            required=True,
            max_length=10
        )

        self.add_item(self.rations_input)
        self.add_item(self.cloth_input)
        self.add_item(self.platinum_input)

    async def on_submit(self, interaction: discord.Interaction):
        from helpers import emotive_message
        from embeds import create_edit_unit_embed

        try:
            rations = int(self.rations_input.value.strip())
            cloth = int(self.cloth_input.value.strip())
            platinum = int(self.platinum_input.value.strip())

            if any(v < 0 for v in [rations, cloth, platinum]):
                await interaction.response.send_message(
                    emotive_message("All resource values must be >= 0."),
                    ephemeral=True
                )
                return
        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid values. Resource fields must be integers."),
                ephemeral=True
            )
            return

        async with self.db_pool.acquire() as conn:
            self.unit.upkeep_rations = rations
            self.unit.upkeep_cloth = cloth
            self.unit.upkeep_platinum = platinum
            await self.unit.upsert(conn)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit upkeep (rations/cloth/platinum) for '{self.unit.unit_id}' in guild {interaction.guild_id}")

        new_embed = create_edit_unit_embed(self.unit, naval_positions=self.parent_view.naval_positions)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class EditUnitKeywordsModal(discord.ui.Modal, title="Edit Keywords"):
    """Modal for editing unit keywords."""

    def __init__(self, unit: Unit, db_pool, parent_view):
        super().__init__()
        self.unit = unit
        self.db_pool = db_pool
        self.parent_view = parent_view

        self.keywords_input = discord.ui.TextInput(
            label="Keywords (comma-separated)",
            default=", ".join(unit.keywords) if unit.keywords else "",
            required=False,
            max_length=500,
            style=discord.TextStyle.paragraph
        )

        self.add_item(self.keywords_input)

    async def on_submit(self, interaction: discord.Interaction):
        from helpers import emotive_message
        from embeds import create_edit_unit_embed

        # Parse keywords
        keywords_str = self.keywords_input.value.strip()
        if keywords_str:
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        else:
            keywords = []

        async with self.db_pool.acquire() as conn:
            self.unit.keywords = keywords
            await self.unit.upsert(conn)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit keywords for '{self.unit.unit_id}' in guild {interaction.guild_id}")

        new_embed = create_edit_unit_embed(self.unit, naval_positions=self.parent_view.naval_positions)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class EditUnitView(discord.ui.View):
    """View with buttons to edit unit field categories."""

    def __init__(self, unit: Unit, db_pool, naval_positions=None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.unit = unit
        self.db_pool = db_pool
        self.naval_positions = naval_positions

    @discord.ui.button(label="Basic Info", style=discord.ButtonStyle.primary, row=0)
    async def basic_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditUnitBasicModal(self.unit, self.db_pool, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Location", style=discord.ButtonStyle.secondary, row=0)
    async def location(self, interaction: discord.Interaction, button: discord.ui.Button):
        naval_positions_str = ""
        if self.unit.is_naval:
            async with self.db_pool.acquire() as conn:
                territories = await NavalUnitPosition.fetch_territories_by_unit(conn, self.unit.id, interaction.guild_id)
                naval_positions_str = ", ".join(territories)
        modal = EditUnitLocationModal(self.unit, self.db_pool, self, naval_positions_str)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Ownership", style=discord.ButtonStyle.secondary, row=0)
    async def ownership(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Need to fetch current owner/faction identifiers for display
        async with self.db_pool.acquire() as conn:
            owner_char_identifier = ""
            owner_faction_id = ""
            faction_id = ""

            if self.unit.owner_character_id:
                char = await Character.fetch_by_id(conn, self.unit.owner_character_id)
                if char:
                    owner_char_identifier = char.identifier

            if self.unit.owner_faction_id:
                faction = await Faction.fetch_by_id(conn, self.unit.owner_faction_id)
                if faction:
                    owner_faction_id = faction.faction_id

            if self.unit.faction_id:
                faction = await Faction.fetch_by_id(conn, self.unit.faction_id)
                if faction:
                    faction_id = faction.faction_id

        modal = EditUnitOwnershipModal(self.unit, self.db_pool, self, owner_char_identifier, owner_faction_id, faction_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Commander", style=discord.ButtonStyle.secondary, row=0)
    async def commander(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Fetch current commander identifier for display
        commander_identifier = ""
        if self.unit.commander_character_id:
            async with self.db_pool.acquire() as conn:
                char = await Character.fetch_by_id(conn, self.unit.commander_character_id)
                if char:
                    commander_identifier = char.identifier

        modal = EditUnitCommanderModal(self.unit, self.db_pool, self, commander_identifier)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Combat", style=discord.ButtonStyle.primary, row=1)
    async def combat(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditUnitCombatModal(self.unit, self.db_pool, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Size/Siege", style=discord.ButtonStyle.primary, row=1)
    async def size_siege(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditUnitSizeModal(self.unit, self.db_pool, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Upkeep 1", style=discord.ButtonStyle.secondary, row=1)
    async def upkeep1(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditUnitUpkeep1Modal(self.unit, self.db_pool, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Upkeep 2", style=discord.ButtonStyle.secondary, row=1)
    async def upkeep2(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditUnitUpkeep2Modal(self.unit, self.db_pool, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Keywords", style=discord.ButtonStyle.secondary, row=2)
    async def keywords(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditUnitKeywordsModal(self.unit, self.db_pool, self)
        await interaction.response.send_modal(modal)


class EditUnitTypeBasicModal(discord.ui.Modal, title="Edit Basic Info"):
    """Modal for editing unit type basic info."""

    def __init__(self, unit_type: UnitType, db_pool, parent_view):
        super().__init__()
        self.unit_type = unit_type
        self.db_pool = db_pool
        self.parent_view = parent_view

        self.type_id_input = discord.ui.TextInput(
            label="Type ID",
            default=unit_type.type_id,
            required=True,
            max_length=100
        )
        self.name_input = discord.ui.TextInput(
            label="Name",
            default=unit_type.name,
            required=True,
            max_length=255
        )
        self.nation_input = discord.ui.TextInput(
            label="Nation (leave empty for any nation)",
            default=unit_type.nation or "",
            required=False,
            max_length=50
        )
        self.naval_input = discord.ui.TextInput(
            label="Naval unit? (yes/no)",
            default="yes" if unit_type.is_naval else "no",
            required=True,
            max_length=3
        )

        self.add_item(self.type_id_input)
        self.add_item(self.name_input)
        self.add_item(self.nation_input)
        self.add_item(self.naval_input)

    async def on_submit(self, interaction: discord.Interaction):
        from helpers import emotive_message
        from embeds import create_edit_unit_type_embed
        from db import Unit

        new_type_id = self.type_id_input.value.strip()
        new_name = self.name_input.value.strip()
        new_nation = self.nation_input.value.strip() or None

        # Validate naval flag
        naval_str = self.naval_input.value.strip().lower()
        if naval_str not in ['yes', 'no']:
            await interaction.response.send_message(
                emotive_message("Naval flag must be 'yes' or 'no'."),
                ephemeral=True
            )
            return
        new_naval = naval_str == 'yes'

        # Validate required fields
        if not new_name:
            await interaction.response.send_message(
                emotive_message("Name cannot be empty."),
                ephemeral=True
            )
            return

        async with self.db_pool.acquire() as conn:
            # Check if renaming type_id
            if new_type_id != self.unit_type.type_id:
                # Check if new type_id already exists
                existing = await UnitType.fetch_by_type_id(conn, new_type_id, interaction.guild_id)
                if existing:
                    await interaction.response.send_message(
                        emotive_message(f"Type ID '{new_type_id}' already exists."),
                        ephemeral=True
                    )
                    return

                # Check if any units use this type
                units_using = await conn.fetch(
                    "SELECT unit_id FROM Unit WHERE unit_type = $1 AND guild_id = $2",
                    self.unit_type.type_id, interaction.guild_id
                )
                if units_using:
                    # Update all units to use the new type_id
                    await conn.execute(
                        "UPDATE Unit SET unit_type = $1 WHERE unit_type = $2 AND guild_id = $3",
                        new_type_id, self.unit_type.type_id, interaction.guild_id
                    )

                # Delete old type and update the type_id
                await UnitType.delete(conn, self.unit_type.type_id, interaction.guild_id)
                self.unit_type.type_id = new_type_id

            self.unit_type.name = new_name
            self.unit_type.nation = new_nation
            self.unit_type.is_naval = new_naval
            await self.unit_type.upsert(conn)

        # Update parent view's unit_type reference
        self.parent_view.unit_type = self.unit_type

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit type basic info for '{self.unit_type.type_id}' in guild {interaction.guild_id}")

        new_embed = create_edit_unit_type_embed(self.unit_type)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class EditUnitTypeCombatModal(discord.ui.Modal, title="Edit Combat Stats"):
    """Modal for editing unit type combat stats."""

    def __init__(self, unit_type: UnitType, db_pool, parent_view):
        super().__init__()
        self.unit_type = unit_type
        self.db_pool = db_pool
        self.parent_view = parent_view

        self.movement_input = discord.ui.TextInput(
            label="Movement",
            default=str(unit_type.movement),
            required=True,
            max_length=10
        )
        self.organization_input = discord.ui.TextInput(
            label="Organization",
            default=str(unit_type.organization),
            required=True,
            max_length=10
        )
        self.attack_input = discord.ui.TextInput(
            label="Attack",
            default=str(unit_type.attack),
            required=True,
            max_length=10
        )
        self.defense_input = discord.ui.TextInput(
            label="Defense",
            default=str(unit_type.defense),
            required=True,
            max_length=10
        )

        self.add_item(self.movement_input)
        self.add_item(self.organization_input)
        self.add_item(self.attack_input)
        self.add_item(self.defense_input)

    async def on_submit(self, interaction: discord.Interaction):
        from helpers import emotive_message
        from embeds import create_edit_unit_type_embed

        try:
            movement = int(self.movement_input.value.strip())
            organization = int(self.organization_input.value.strip())
            attack = int(self.attack_input.value.strip())
            defense = int(self.defense_input.value.strip())

            if any(x < 0 for x in [movement, organization, attack, defense]):
                await interaction.response.send_message(
                    emotive_message("Stats cannot be negative."),
                    ephemeral=True
                )
                return

        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid stat values. Use integers."),
                ephemeral=True
            )
            return

        async with self.db_pool.acquire() as conn:
            self.unit_type.movement = movement
            self.unit_type.organization = organization
            self.unit_type.attack = attack
            self.unit_type.defense = defense
            await self.unit_type.upsert(conn)

        self.parent_view.unit_type = self.unit_type

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit type combat stats for '{self.unit_type.type_id}' in guild {interaction.guild_id}")

        new_embed = create_edit_unit_type_embed(self.unit_type)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class EditUnitTypeSizeModal(discord.ui.Modal, title="Edit Size/Siege Stats"):
    """Modal for editing unit type size and siege stats."""

    def __init__(self, unit_type: UnitType, db_pool, parent_view):
        super().__init__()
        self.unit_type = unit_type
        self.db_pool = db_pool
        self.parent_view = parent_view

        self.siege_attack_input = discord.ui.TextInput(
            label="Siege Attack",
            default=str(unit_type.siege_attack),
            required=True,
            max_length=10
        )
        self.siege_defense_input = discord.ui.TextInput(
            label="Siege Defense",
            default=str(unit_type.siege_defense),
            required=True,
            max_length=10
        )
        self.size_input = discord.ui.TextInput(
            label="Size",
            default=str(unit_type.size),
            required=True,
            max_length=10
        )
        self.capacity_input = discord.ui.TextInput(
            label="Capacity",
            default=str(unit_type.capacity),
            required=True,
            max_length=10
        )

        self.add_item(self.siege_attack_input)
        self.add_item(self.siege_defense_input)
        self.add_item(self.size_input)
        self.add_item(self.capacity_input)

    async def on_submit(self, interaction: discord.Interaction):
        from helpers import emotive_message
        from embeds import create_edit_unit_type_embed

        try:
            siege_attack = int(self.siege_attack_input.value.strip())
            siege_defense = int(self.siege_defense_input.value.strip())
            size = int(self.size_input.value.strip())
            capacity = int(self.capacity_input.value.strip())

            if any(x < 0 for x in [siege_attack, siege_defense, size, capacity]):
                await interaction.response.send_message(
                    emotive_message("Stats cannot be negative."),
                    ephemeral=True
                )
                return

        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid stat values. Use integers."),
                ephemeral=True
            )
            return

        async with self.db_pool.acquire() as conn:
            self.unit_type.siege_attack = siege_attack
            self.unit_type.siege_defense = siege_defense
            self.unit_type.size = size
            self.unit_type.capacity = capacity
            await self.unit_type.upsert(conn)

        self.parent_view.unit_type = self.unit_type

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit type size/siege stats for '{self.unit_type.type_id}' in guild {interaction.guild_id}")

        new_embed = create_edit_unit_type_embed(self.unit_type)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class EditUnitTypeCostModal(discord.ui.Modal, title="Edit Cost"):
    """Modal for editing unit type cost."""

    def __init__(self, unit_type: UnitType, db_pool, parent_view):
        super().__init__()
        self.unit_type = unit_type
        self.db_pool = db_pool
        self.parent_view = parent_view

        cost_str = f"{unit_type.cost_ore},{unit_type.cost_lumber},{unit_type.cost_coal},{unit_type.cost_rations},{unit_type.cost_cloth},{unit_type.cost_platinum}"
        self.cost_input = discord.ui.TextInput(
            label="Cost (ore,lumber,coal,rations,cloth,plat)",
            placeholder="e.g., 5,2,0,10,5,0",
            default=cost_str,
            required=True,
            max_length=50
        )

        self.add_item(self.cost_input)

    async def on_submit(self, interaction: discord.Interaction):
        from helpers import emotive_message
        from embeds import create_edit_unit_type_embed

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

        async with self.db_pool.acquire() as conn:
            self.unit_type.cost_ore = cost_ore
            self.unit_type.cost_lumber = cost_lumber
            self.unit_type.cost_coal = cost_coal
            self.unit_type.cost_rations = cost_rations
            self.unit_type.cost_cloth = cost_cloth
            self.unit_type.cost_platinum = cost_platinum
            await self.unit_type.upsert(conn)

        self.parent_view.unit_type = self.unit_type

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit type cost for '{self.unit_type.type_id}' in guild {interaction.guild_id}")

        new_embed = create_edit_unit_type_embed(self.unit_type)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class EditUnitTypeUpkeepModal(discord.ui.Modal, title="Edit Upkeep"):
    """Modal for editing unit type upkeep."""

    def __init__(self, unit_type: UnitType, db_pool, parent_view):
        super().__init__()
        self.unit_type = unit_type
        self.db_pool = db_pool
        self.parent_view = parent_view

        upkeep_str = f"{unit_type.upkeep_ore},{unit_type.upkeep_lumber},{unit_type.upkeep_coal},{unit_type.upkeep_rations},{unit_type.upkeep_cloth},{unit_type.upkeep_platinum}"
        self.upkeep_input = discord.ui.TextInput(
            label="Upkeep (ore,lumber,coal,rations,cloth,plat)",
            placeholder="e.g., 0,0,0,2,1,0",
            default=upkeep_str,
            required=True,
            max_length=50
        )

        self.add_item(self.upkeep_input)

    async def on_submit(self, interaction: discord.Interaction):
        from helpers import emotive_message
        from embeds import create_edit_unit_type_embed

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

        async with self.db_pool.acquire() as conn:
            self.unit_type.upkeep_ore = upkeep_ore
            self.unit_type.upkeep_lumber = upkeep_lumber
            self.unit_type.upkeep_coal = upkeep_coal
            self.unit_type.upkeep_rations = upkeep_rations
            self.unit_type.upkeep_cloth = upkeep_cloth
            self.unit_type.upkeep_platinum = upkeep_platinum
            await self.unit_type.upsert(conn)

        self.parent_view.unit_type = self.unit_type

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit type upkeep for '{self.unit_type.type_id}' in guild {interaction.guild_id}")

        new_embed = create_edit_unit_type_embed(self.unit_type)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class EditUnitTypeKeywordsModal(discord.ui.Modal, title="Edit Keywords"):
    """Modal for editing unit type keywords."""

    def __init__(self, unit_type: UnitType, db_pool, parent_view):
        super().__init__()
        self.unit_type = unit_type
        self.db_pool = db_pool
        self.parent_view = parent_view

        self.keywords_input = discord.ui.TextInput(
            label="Keywords (comma-separated)",
            default=", ".join(unit_type.keywords) if unit_type.keywords else "",
            required=False,
            max_length=500,
            style=discord.TextStyle.paragraph
        )

        self.add_item(self.keywords_input)

    async def on_submit(self, interaction: discord.Interaction):
        from helpers import emotive_message
        from embeds import create_edit_unit_type_embed

        # Parse keywords
        keywords_str = self.keywords_input.value.strip()
        if keywords_str:
            keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
        else:
            keywords = []

        async with self.db_pool.acquire() as conn:
            self.unit_type.keywords = keywords
            await self.unit_type.upsert(conn)

        self.parent_view.unit_type = self.unit_type

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit type keywords for '{self.unit_type.type_id}' in guild {interaction.guild_id}")

        new_embed = create_edit_unit_type_embed(self.unit_type)
        await interaction.response.edit_message(embed=new_embed, view=self.parent_view)


class EditUnitTypeView(discord.ui.View):
    """View with buttons to edit unit type field categories."""

    def __init__(self, unit_type: UnitType, db_pool):
        super().__init__(timeout=300)  # 5 minute timeout
        self.unit_type = unit_type
        self.db_pool = db_pool

    @discord.ui.button(label="Basic Info", style=discord.ButtonStyle.primary, row=0)
    async def basic_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditUnitTypeBasicModal(self.unit_type, self.db_pool, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Combat", style=discord.ButtonStyle.primary, row=0)
    async def combat(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditUnitTypeCombatModal(self.unit_type, self.db_pool, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Size/Siege", style=discord.ButtonStyle.primary, row=0)
    async def size_siege(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditUnitTypeSizeModal(self.unit_type, self.db_pool, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Cost", style=discord.ButtonStyle.secondary, row=1)
    async def cost(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditUnitTypeCostModal(self.unit_type, self.db_pool, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Upkeep", style=discord.ButtonStyle.secondary, row=1)
    async def upkeep(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditUnitTypeUpkeepModal(self.unit_type, self.db_pool, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Keywords", style=discord.ButtonStyle.secondary, row=1)
    async def keywords(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditUnitTypeKeywordsModal(self.unit_type, self.db_pool, self)
        await interaction.response.send_modal(modal)
