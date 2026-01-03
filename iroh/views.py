"""
Discord UI components (modals, views, buttons) for Iroh wargame bot.
"""
import discord
from typing import Optional
from db import Territory, UnitType, PlayerResources, Character, WargameConfig
import handlers
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
        production_str = f"{territory.ore_production},{territory.lumber_production},{territory.coal_production},{territory.rations_production},{territory.cloth_production}"
        self.production_input = discord.ui.TextInput(
            label="Production (ore,lumber,coal,rations,cloth)",
            placeholder="e.g., 5,3,2,8,4",
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
            if len(production_parts) != 5:
                await interaction.response.send_message(
                    emotive_message("Production must have exactly 5 values (ore, lumber, coal, rations, cloth)."),
                    ephemeral=True
                )
                return

            ore, lumber, coal, rations, cloth = production_parts

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

    def __init__(self, unit_type: Optional[UnitType] = None, type_id: str = None, name: str = None, nation: str = None, db_pool = None):
        super().__init__()
        self.unit_type = unit_type
        self.type_id = type_id
        self.name_value = name
        self.nation = nation
        self.db_pool = db_pool

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

        # Cost field (ore,lumber,coal,rations,cloth)
        if unit_type:
            cost_str = f"{unit_type.cost_ore},{unit_type.cost_lumber},{unit_type.cost_coal},{unit_type.cost_rations},{unit_type.cost_cloth}"
        else:
            cost_str = "5,2,0,10,5"

        self.cost_input = discord.ui.TextInput(
            label="Cost (ore,lumber,coal,rations,cloth)",
            placeholder="e.g., 5,2,0,10,5",
            default=cost_str,
            required=True,
            max_length=50
        )
        self.add_item(self.cost_input)

        # Upkeep field (ore,lumber,coal,rations,cloth)
        if unit_type:
            upkeep_str = f"{unit_type.upkeep_ore},{unit_type.upkeep_lumber},{unit_type.upkeep_coal},{unit_type.upkeep_rations},{unit_type.upkeep_cloth}"
        else:
            upkeep_str = "0,0,0,2,1"

        self.upkeep_input = discord.ui.TextInput(
            label="Upkeep (ore,lumber,coal,rations,cloth)",
            placeholder="e.g., 0,0,0,2,1",
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
            if len(cost_parts) != 5:
                await interaction.response.send_message(
                    emotive_message("Cost must have exactly 5 values (ore, lumber, coal, rations, cloth)."),
                    ephemeral=True
                )
                return

            cost_ore, cost_lumber, cost_coal, cost_rations, cost_cloth = cost_parts

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
            if len(upkeep_parts) != 5:
                await interaction.response.send_message(
                    emotive_message("Upkeep must have exactly 5 values (ore, lumber, coal, rations, cloth)."),
                    ephemeral=True
                )
                return

            upkeep_ore, upkeep_lumber, upkeep_coal, upkeep_rations, upkeep_cloth = upkeep_parts

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

        # Update or create unit type
        if self.unit_type:
            # Update existing
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
            self.unit_type.upkeep_ore = upkeep_ore
            self.unit_type.upkeep_lumber = upkeep_lumber
            self.unit_type.upkeep_coal = upkeep_coal
            self.unit_type.upkeep_rations = upkeep_rations
            self.unit_type.upkeep_cloth = upkeep_cloth
            self.unit_type.is_naval = is_naval

            # Save to database
            async with self.db_pool.acquire() as conn:
                await self.unit_type.upsert(conn)

            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited unit type '{self.unit_type.type_id}' (nation: {self.unit_type.nation}) via modal in guild {interaction.guild_id}")

            await interaction.response.send_message(
                emotive_message(f"Unit type '{self.unit_type.name}' updated successfully."),
                ephemeral=False
            )
        else:
            # Create new
            unit_type = UnitType(
                type_id=self.type_id,
                name=self.name_value,
                nation=self.nation,
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
                upkeep_ore=upkeep_ore,
                upkeep_lumber=upkeep_lumber,
                upkeep_coal=upkeep_coal,
                upkeep_rations=upkeep_rations,
                upkeep_cloth=upkeep_cloth,
                is_naval=is_naval,
                keywords=[],
                guild_id=interaction.guild_id
            )

            # Save to database
            async with self.db_pool.acquire() as conn:
                await unit_type.upsert(conn)

            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) created unit type '{self.type_id}' (name: {self.name_value}, nation: {self.nation}) via modal in guild {interaction.guild_id}")

            await interaction.response.send_message(
                emotive_message(f"Unit type '{self.name_value}' created successfully."),
                ephemeral=False
            )


class ModifyResourcesModal(discord.ui.Modal, title="Modify Player Resources"):
    """Modal for modifying player resources."""

    def __init__(self, character: Character, resources: PlayerResources, db_pool):
        super().__init__()
        self.character = character
        self.resources = resources
        self.db_pool = db_pool

        # Resource fields
        self.ore_input = discord.ui.TextInput(
            label="Ore",
            default=str(resources.ore),
            required=True,
            max_length=10
        )
        self.add_item(self.ore_input)

        self.lumber_input = discord.ui.TextInput(
            label="Lumber",
            default=str(resources.lumber),
            required=True,
            max_length=10
        )
        self.add_item(self.lumber_input)

        self.coal_input = discord.ui.TextInput(
            label="Coal",
            default=str(resources.coal),
            required=True,
            max_length=10
        )
        self.add_item(self.coal_input)

        self.rations_input = discord.ui.TextInput(
            label="Rations",
            default=str(resources.rations),
            required=True,
            max_length=10
        )
        self.add_item(self.rations_input)

        self.cloth_input = discord.ui.TextInput(
            label="Cloth",
            default=str(resources.cloth),
            required=True,
            max_length=10
        )
        self.add_item(self.cloth_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission."""
        from helpers import emotive_message

        # Parse values
        try:
            ore = int(self.ore_input.value.strip())
            lumber = int(self.lumber_input.value.strip())
            coal = int(self.coal_input.value.strip())
            rations = int(self.rations_input.value.strip())
            cloth = int(self.cloth_input.value.strip())

            if any(x < 0 for x in [ore, lumber, coal, rations, cloth]):
                await interaction.response.send_message(
                    emotive_message("Resource values cannot be negative."),
                    ephemeral=True
                )
                return

        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid resource values. Use integers only."),
                ephemeral=True
            )
            return

        # Update resources
        self.resources.ore = ore
        self.resources.lumber = lumber
        self.resources.coal = coal
        self.resources.rations = rations
        self.resources.cloth = cloth

        # Save to database
        async with self.db_pool.acquire() as conn:
            await self.resources.upsert(conn)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) modified resources for character '{self.character.name}' via modal in guild {interaction.guild_id} (ore: {ore}, lumber: {lumber}, coal: {coal}, rations: {rations}, cloth: {cloth})")

        await interaction.response.send_message(
            emotive_message(f"Resources for {self.character.name} updated successfully."),
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


class ResourceTransferModal(discord.ui.Modal, title="Resource Transfer Order"):
    """Modal for submitting a resource transfer order."""

    def __init__(self, from_character: Character, db_pool):
        super().__init__()
        self.from_character = from_character
        self.db_pool = db_pool

        # Recipient character identifier
        self.recipient_input = discord.ui.TextInput(
            label="Recipient Character Identifier",
            placeholder="e.g., 'zuko' or 'iroh'",
            required=True,
            max_length=100
        )
        self.add_item(self.recipient_input)

        # Resources field (comma-separated)
        self.resources_input = discord.ui.TextInput(
            label="Resources (ore,lumber,coal,rations,cloth)",
            placeholder="e.g., 10,5,0,0,0",
            required=True,
            max_length=50
        )
        self.add_item(self.resources_input)

        # Transfer type
        self.transfer_type_input = discord.ui.TextInput(
            label="Transfer Type (one-time / ongoing)",
            placeholder="one-time or ongoing",
            default="one-time",
            required=True,
            max_length=10
        )
        self.add_item(self.transfer_type_input)

        # Term (for ongoing transfers)
        self.term_input = discord.ui.TextInput(
            label="Term (ongoing only, empty = indefinite)",
            placeholder="Number of turns, or leave empty",
            required=False,
            max_length=10
        )
        self.add_item(self.term_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission."""
        from helpers import emotive_message

        # Parse recipient
        recipient_identifier = self.recipient_input.value.strip()

        # Parse resources
        try:
            resource_parts = [int(x.strip()) for x in self.resources_input.value.split(',')]
            if len(resource_parts) != 5:
                await interaction.response.send_message(
                    emotive_message("Resources must have exactly 5 values (ore, lumber, coal, rations, cloth)."),
                    ephemeral=True
                )
                return

            ore, lumber, coal, rations, cloth = resource_parts

            if any(x < 0 for x in resource_parts):
                await interaction.response.send_message(
                    emotive_message("Resource values cannot be negative."),
                    ephemeral=True
                )
                return

        except ValueError:
            await interaction.response.send_message(
                emotive_message("Invalid resource values. Use integers separated by commas."),
                ephemeral=True
            )
            return

        # Parse transfer type
        transfer_type = self.transfer_type_input.value.strip().lower()
        if transfer_type not in ['one-time', 'ongoing']:
            await interaction.response.send_message(
                emotive_message("Transfer type must be 'one-time' or 'ongoing'."),
                ephemeral=True
            )
            return

        is_ongoing = transfer_type == 'ongoing'

        # Parse term
        term = None
        if self.term_input.value.strip():
            try:
                term = int(self.term_input.value.strip())
                if term < 2:
                    await interaction.response.send_message(
                        emotive_message("Term must be at least 2 turns if specified."),
                        ephemeral=True
                    )
                    return
            except ValueError:
                await interaction.response.send_message(
                    emotive_message("Invalid term value. Use an integer or leave empty."),
                    ephemeral=True
                )
                return

        # Build resources dict
        resources = {
            'ore': ore,
            'lumber': lumber,
            'coal': coal,
            'rations': rations,
            'cloth': cloth
        }

        # Submit order via handler
        async with self.db_pool.acquire() as conn:
            success, message = await handlers.submit_resource_transfer_order(
                conn,
                self.from_character,
                recipient_identifier,
                resources,
                is_ongoing,
                term,
                interaction.guild_id
            )

        if success:
            logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) submitted resource transfer order from '{self.from_character.name}' to '{recipient_identifier}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"User {interaction.user.name} (ID: {interaction.user.id}) failed to submit resource transfer order: {message}")

        await interaction.response.send_message(
            emotive_message(message),
            ephemeral=not success
        )
