import discord
from discord import app_commands
from discord.ext import commands, tasks
from helpers import *
from embeds import *
from views import *
import handlers
import turn_embeds
import os
import logging
from dotenv import load_dotenv
from db import *
import asyncpg

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


# Helper function to check admin permissions
def is_admin(interaction: discord.Interaction) -> bool:
    """Check if user has manage_guild permission"""
    return interaction.user.guild_permissions.manage_guild


# View Commands - Player accessible
@tree.command(
    name="view-territory",
    description="View detailed information about a territory"
)
@app_commands.describe(territory_id="The territory ID to view")
async def view_territory_cmd(interaction: discord.Interaction, territory_id: int):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_territory(conn, territory_id, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create and send embed
        embed = create_territory_embed(data['territory'], data['adjacent_ids'], data['controller_name'])
        await interaction.followup.send(embed=embed)


@tree.command(
    name="view-faction",
    description="View detailed information about a faction"
)
@app_commands.describe(faction_id="The faction ID to view")
async def view_faction_cmd(interaction: discord.Interaction, faction_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        admin = is_admin(interaction)
        success, message, data = await handlers.view_faction(conn, faction_id, interaction.guild_id, admin)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create and send embed
        if admin:
            embed = create_faction_embed(data['faction'], data['members'], data['leader'])
        else:
            # Limited info for non-admins
            embed = discord.Embed(
                title=f"⚔️ {data['faction'].name}",
                description=f"Faction ID: `{data['faction'].faction_id}`",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Information",
                value="Full faction details are only visible to server administrators.",
                inline=False
            )

        await interaction.followup.send(embed=embed)


@tree.command(
    name="view-unit",
    description="View detailed information about a unit"
)
@app_commands.describe(unit_id="The unit ID to view")
async def view_unit_cmd(interaction: discord.Interaction, unit_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        admin = is_admin(interaction)
        success, message, data = await handlers.view_unit(conn, unit_id, interaction.guild_id, admin)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create and send embed
        embed = create_unit_embed(
            data['unit'],
            data['unit_type'],
            data['owner'],
            data['commander'],
            data['faction'],
            show_full_details=admin
        )
        await interaction.followup.send(embed=embed)


@tree.command(
    name="view-unit-type",
    description="View detailed information about a unit type"
)
@app_commands.describe(
    type_id="The unit type ID to view",
    nation="Optional: The nation (leave empty for nation-agnostic types)"
)
async def view_unit_type_cmd(interaction: discord.Interaction, type_id: str, nation: str = None):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_unit_type(conn, type_id, nation, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create and send embed
        embed = create_unit_type_embed(data['unit_type'])
        await interaction.followup.send(embed=embed)


@tree.command(
    name="my-resources",
    description="View your character's resource inventory"
)
async def my_resources_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_resources(conn, interaction.user.id, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create and send embed
        embed = create_resources_embed(data['character'], data['resources'])
        await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(
    name="my-faction",
    description="View your character's faction membership"
)
async def my_faction_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_faction_membership(conn, interaction.user.id, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create and send embed
        embed = create_faction_embed(data['faction'], data['members'], data['leader'])
        embed.description = f"Your character's faction\nFaction ID: `{data['faction'].faction_id}`"
        await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(
    name="my-units",
    description="View units your character owns or commands"
)
async def my_units_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_units_for_character(conn, interaction.user.id, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Combine and deduplicate
        all_units = {unit.id: unit for unit in data['owned_units'] + data['commanded_units']}.values()

        # Create summary embed
        embed = discord.Embed(
            title=f"🎖️ {data['character'].name}'s Units",
            color=discord.Color.blue()
        )

        owned_list = []
        commanded_list = []

        for unit in all_units:
            unit_str = f"`{unit.unit_id}`: {unit.name or unit.unit_type}"
            if unit.current_territory_id is not None:
                unit_str += f" (Territory {unit.current_territory_id})"

            if unit.owner_character_id == data['character'].id:
                owned_list.append(unit_str)
            if unit.commander_character_id == data['character'].id:
                commanded_list.append(unit_str)

        if owned_list:
            embed.add_field(
                name=f"Owned Units ({len(owned_list)})",
                value="\n".join(owned_list),
                inline=False
            )

        if commanded_list:
            embed.add_field(
                name=f"Commanded Units ({len(commanded_list)})",
                value="\n".join(commanded_list),
                inline=False
            )

        embed.set_footer(text="Use /view-unit <unit_id> to see detailed unit information")

        await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(
    name="my-territories",
    description="View territories controlled by your character"
)
async def my_territories_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_territories_for_character(conn, interaction.user.id, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create summary embed
        character_name = data['character'].name
        embed = discord.Embed(
            title=f"🗺️ {character_name}'s Territories",
            description=f"{len(data['territories'])} territories controlled",
            color=discord.Color.green()
        )

        territory_list = []
        for territory in data['territories']:
            adjacent_ids = data['adjacencies'].get(territory.territory_id, [])

            # Calculate total production
            total_prod = (territory.ore_production + territory.lumber_production +
                         territory.coal_production + territory.rations_production +
                         territory.cloth_production)

            terr_str = f"**{territory.territory_id}**: {territory.name or 'Unnamed'} ({territory.terrain_type})\n"
            terr_str += f"  Production: {total_prod}/turn | Adjacent: {', '.join(str(t) for t in sorted(adjacent_ids)) if adjacent_ids else 'None'}"

            territory_list.append(terr_str)

        # Split into chunks if too many
        if len(territory_list) <= 10:
            embed.add_field(
                name="Controlled Territories",
                value="\n\n".join(territory_list),
                inline=False
            )
        else:
            embed.add_field(
                name="Controlled Territories (first 10)",
                value="\n\n".join(territory_list[:10]) + f"\n\n... and {len(territory_list) - 10} more",
                inline=False
            )

        embed.set_footer(text="Use /view-territory <territory_id> for detailed information")

        await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(
    name="my-units-list",
    description="List IDs of units you own or command"
)
async def my_units_list_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_units_for_character(conn, interaction.user.id, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Combine and deduplicate
        all_units = {unit.id: unit for unit in data['owned_units'] + data['commanded_units']}.values()

        # Create list of unit IDs
        unit_ids = [unit.unit_id for unit in all_units]

        await interaction.followup.send(
            f"**Your unit IDs:**\n`{', '.join(unit_ids)}`\n\nUse `/view-unit <unit_id>` for details.",
            ephemeral=True
        )


@tree.command(
    name="my-territories-list",
    description="List IDs of territories controlled by your character"
)
async def my_territories_list_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_territories_for_character(conn, interaction.user.id, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create list of territory IDs
        territory_ids = [str(t.territory_id) for t in data['territories']]
        character_name = data['character'].name

        await interaction.followup.send(
            f"**{character_name}'s territory IDs:**\n`{', '.join(territory_ids)}`\n\nUse `/view-territory <territory_id>` for details.",
            ephemeral=True
        )


# Admin Commands
@tree.command(
    name="clear-wargame-config",
    description="[Admin] Clear all wargame data (factions, territories, units, etc.)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def clear_wargame_config(interaction: discord.Interaction):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Delete in reverse order of dependencies
        await conn.execute("DELETE FROM Unit WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM Territory WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM Faction WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", interaction.guild_id)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) cleared all wargame config for guild {interaction.guild_id}")

        await interaction.followup.send(
            emotive_message("All wargame configuration has been cleared. The slate is clean.")
        )


@tree.command(
    name="list-factions",
    description="[Admin] List all faction IDs in this server"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def list_factions_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.list_factions(conn, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message))
            return

        faction_list = []
        for item in data:
            faction_list.append(f"`{item['faction'].faction_id}`: {item['faction'].name} ({item['member_count']} members)")

        embed = discord.Embed(
            title="⚔️ All Factions",
            description="\n".join(faction_list),
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Total: {len(data)} factions")

        await interaction.followup.send(embed=embed)


@tree.command(
    name="list-territories",
    description="[Admin] List all territory IDs in this server"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def list_territories_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.list_territories(conn, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message))
            return

        territory_list = []
        for item in data:
            territory = item['territory']
            territory_list.append(
                f"`{territory.territory_id}`: {territory.name or 'Unnamed'} ({territory.terrain_type}) - {item['controller_name']}"
            )

        embed = discord.Embed(
            title="🗺️ All Territories",
            description="\n".join(territory_list),
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Total: {len(data)} territories")

        await interaction.followup.send(embed=embed)


@tree.command(
    name="list-unit-types",
    description="[Admin] List all unit type IDs in this server"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def list_unit_types_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.list_unit_types(conn, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message))
            return

        unit_type_list = []
        for unit_type in data:
            nation_str = f" ({unit_type.nation})" if unit_type.nation else " (any nation)"
            unit_type_list.append(f"`{unit_type.type_id}`: {unit_type.name}{nation_str}")

        embed = discord.Embed(
            title="📋 All Unit Types",
            description="\n".join(unit_type_list),
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Total: {len(data)} unit types")

        await interaction.followup.send(embed=embed)


@tree.command(
    name="list-units",
    description="[Admin] List all unit IDs in this server"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def list_units_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.list_units(conn, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message))
            return

        unit_list = []
        for item in data:
            unit = item['unit']
            location = f"Territory {unit.current_territory_id}" if unit.current_territory_id is not None else "Undeployed"
            unit_list.append(
                f"`{unit.unit_id}`: {unit.name or unit.unit_type} - {item['faction_name']} - {location} (Owner: {item['owner_name']})"
            )

        # Split into chunks if too many
        if len(unit_list) <= 20:
            embed = discord.Embed(
                title="🎖️ All Units",
                description="\n".join(unit_list),
                color=discord.Color.blue()
            )
        else:
            embed = discord.Embed(
                title="🎖️ All Units (first 20)",
                description="\n".join(unit_list[:20]) + f"\n\n... and {len(unit_list) - 20} more",
                color=discord.Color.blue()
            )

        embed.set_footer(text=f"Total: {len(data)} units")

        await interaction.followup.send(embed=embed)


@tree.command(
    name="create-test-config",
    description="[Admin] Create a test wargame configuration in this server"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def create_test_config(interaction: discord.Interaction):
    await interaction.response.defer()

    from config_manager import ConfigManager
    import os
    import yaml

    # Load test config from file
    test_config_path = os.path.join(os.path.dirname(__file__), 'test_config.yaml')
    try:
        with open(test_config_path, 'r') as f:
            test_config = f.read()
    except FileNotFoundError:
        await interaction.followup.send(
            emotive_message("Test configuration file not found. Please ensure test_config.yaml exists in the iroh directory."),
            ephemeral=True
        )
        return
    except Exception as e:
        await interaction.followup.send(
            emotive_message(f"Error reading test configuration file: {e}"),
            ephemeral=True
        )
        return

    async with db_pool.acquire() as conn:
        success, message = await ConfigManager.import_config(conn, interaction.guild_id, test_config)

        if success:
            # Parse config to count entities
            config_dict = yaml.safe_load(test_config)
            num_factions = len(config_dict.get('factions', []))
            num_territories = len(config_dict.get('territories', []))
            num_unit_types = len(config_dict.get('unit_types', []))
            num_units = len(config_dict.get('units', []))

            created_items = []
            if num_factions:
                created_items.append(f"• {num_factions} faction{'s' if num_factions != 1 else ''}")
            if num_territories:
                created_items.append(f"• {num_territories} territor{'ies' if num_territories != 1 else 'y'}")
            if num_unit_types:
                created_items.append(f"• {num_unit_types} unit type{'s' if num_unit_types != 1 else ''}")
            if num_units:
                created_items.append(f"• {num_units} unit{'s' if num_units != 1 else ''}")

            created_str = '\n'.join(created_items) if created_items else '• (empty config)'

            await interaction.followup.send(
                emotive_message(f"Test wargame configuration created successfully!\n\nCreated:\n{created_str}")
            )
        else:
            await interaction.followup.send(
                emotive_message(f"Failed to create test configuration: {message}"),
                ephemeral=True
            )


# Faction Management Commands
@tree.command(
    name="create-faction",
    description="[Admin] Create a new faction"
)
@app_commands.describe(
    faction_id="Unique identifier for the faction (e.g., 'fire-nation')",
    name="Display name for the faction",
    leader="Optional: Character identifier for the faction leader"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def create_faction_cmd(interaction: discord.Interaction, faction_id: str, name: str, leader: str = None):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.create_faction(conn, faction_id, name, interaction.guild_id, leader)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) created faction '{faction_id}' (name: {name}, leader: {leader}) in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to create faction '{faction_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="delete-faction",
    description="[Admin] Delete a faction"
)
@app_commands.describe(faction_id="The faction ID to delete")
@app_commands.checks.has_permissions(manage_guild=True)
async def delete_faction_cmd(interaction: discord.Interaction, faction_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.delete_faction(conn, faction_id, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) deleted faction '{faction_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to delete faction '{faction_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="set-faction-leader",
    description="[Admin] Change the leader of a faction"
)
@app_commands.describe(
    faction_id="The faction ID",
    leader="Character identifier for the new leader (or 'none' to remove leader)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def set_faction_leader_cmd(interaction: discord.Interaction, faction_id: str, leader: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.set_faction_leader(conn, faction_id, leader, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) set faction leader for '{faction_id}' to '{leader}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to set faction leader for '{faction_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="add-faction-member",
    description="[Admin] Add a member to a faction"
)
@app_commands.describe(
    faction_id="The faction ID",
    character="Character identifier to add"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def add_faction_member_cmd(interaction: discord.Interaction, faction_id: str, character: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.add_faction_member(conn, faction_id, character, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) added character '{character}' to faction '{faction_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to add character '{character}' to faction '{faction_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="remove-faction-member",
    description="[Admin] Remove a member from their faction"
)
@app_commands.describe(character="Character identifier to remove")
@app_commands.checks.has_permissions(manage_guild=True)
async def remove_faction_member_cmd(interaction: discord.Interaction, character: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.remove_faction_member(conn, character, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) removed character '{character}' from faction in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to remove character '{character}' from faction in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


# Territory Management Commands
@tree.command(
    name="create-territory",
    description="[Admin] Create a new territory"
)
@app_commands.describe(
    territory_id="Unique integer ID for the territory",
    terrain_type="Terrain type (plains, mountain, desert, ocean, lake)",
    name="Optional display name for the territory"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def create_territory_cmd(interaction: discord.Interaction, territory_id: int, terrain_type: str, name: str = None):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.create_territory(conn, territory_id, terrain_type, interaction.guild_id, name)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) created territory {territory_id} (name: {name}, type: {terrain_type}) in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to create territory {territory_id} in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="edit-territory",
    description="[Admin] Edit territory properties"
)
@app_commands.describe(territory_id="The territory ID to edit")
@app_commands.checks.has_permissions(manage_guild=True)
async def edit_territory_cmd(interaction: discord.Interaction, territory_id: int):
    async with db_pool.acquire() as conn:
        # Fetch territory for modal
        success, message, territory = await handlers.edit_territory(
            conn, territory_id, interaction.guild_id
        )

        if not success:
            await interaction.response.send_message(
                emotive_message(message),
                ephemeral=True
            )
            return

        # Show modal
        modal = EditTerritoryModal(territory, db_pool)
        await interaction.response.send_modal(modal)


@tree.command(
    name="delete-territory",
    description="[Admin] Delete a territory"
)
@app_commands.describe(territory_id="The territory ID to delete")
@app_commands.checks.has_permissions(manage_guild=True)
async def delete_territory_cmd(interaction: discord.Interaction, territory_id: int):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.delete_territory(conn, territory_id, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) deleted territory {territory_id} in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to delete territory {territory_id} in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="set-territory-controller",
    description="[Admin] Change the faction controlling a territory"
)
@app_commands.describe(
    territory_id="The territory ID",
    faction_id="Faction ID to control the territory (or 'none' for uncontrolled)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def set_territory_controller_cmd(interaction: discord.Interaction, territory_id: int, faction_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.set_territory_controller(conn, territory_id, faction_id, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) set territory {territory_id} controller to '{faction_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to set territory {territory_id} controller in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="add-adjacency",
    description="[Admin] Mark two territories as adjacent"
)
@app_commands.describe(
    territory_id_1="First territory ID",
    territory_id_2="Second territory ID"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def add_adjacency_cmd(interaction: discord.Interaction, territory_id_1: int, territory_id_2: int):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.add_adjacency(conn, territory_id_1, territory_id_2, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) added adjacency between territories {territory_id_1} and {territory_id_2} in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to add adjacency between territories {territory_id_1} and {territory_id_2} in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="remove-adjacency",
    description="[Admin] Remove adjacency between two territories"
)
@app_commands.describe(
    territory_id_1="First territory ID",
    territory_id_2="Second territory ID"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def remove_adjacency_cmd(interaction: discord.Interaction, territory_id_1: int, territory_id_2: int):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.remove_adjacency(conn, territory_id_1, territory_id_2, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) removed adjacency between territories {territory_id_1} and {territory_id_2} in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to remove adjacency between territories {territory_id_1} and {territory_id_2} in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


# Unit Type Management Commands
@tree.command(
    name="create-unit-type",
    description="[Admin] Create a new unit type"
)
@app_commands.describe(
    type_id="Unique identifier for the unit type (e.g., 'infantry')",
    name="Display name for the unit type",
    nation="Optional: Nation that can build this (leave empty for nation-agnostic)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def create_unit_type_cmd(interaction: discord.Interaction, type_id: str, name: str, nation: str = None):
    async with db_pool.acquire() as conn:
        success, message, data = await handlers.create_unit_type(conn, type_id, name, interaction.guild_id, nation)

        if not success:
            await interaction.response.send_message(
                emotive_message(message),
                ephemeral=True
            )
            return

        # Show modal for stats/costs
        modal = EditUnitTypeModal(unit_type=None, type_id=data['type_id'], name=data['name'], nation=data['nation'], db_pool=db_pool)
        await interaction.response.send_modal(modal)


@tree.command(
    name="edit-unit-type",
    description="[Admin] Edit unit type properties"
)
@app_commands.describe(
    type_id="The unit type ID to edit",
    nation="Optional: Nation (leave empty for nation-agnostic types)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def edit_unit_type_cmd(interaction: discord.Interaction, type_id: str, nation: str = None):
    async with db_pool.acquire() as conn:
        success, message, unit_type = await handlers.edit_unit_type(conn, type_id, interaction.guild_id, nation)

        if not success:
            await interaction.response.send_message(
                emotive_message(message),
                ephemeral=True
            )
            return

        # Show modal
        modal = EditUnitTypeModal(unit_type=unit_type, db_pool=db_pool)
        await interaction.response.send_modal(modal)


@tree.command(
    name="delete-unit-type",
    description="[Admin] Delete a unit type"
)
@app_commands.describe(
    type_id="The unit type ID to delete",
    nation="Optional: Nation (leave empty for nation-agnostic types)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def delete_unit_type_cmd(interaction: discord.Interaction, type_id: str, nation: str = None):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.delete_unit_type(conn, type_id, interaction.guild_id, nation)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) deleted unit type '{type_id}' (nation: {nation}) in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to delete unit type '{type_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


# Unit Management Commands
@tree.command(
    name="create-unit",
    description="[Admin] Create a new unit"
)
@app_commands.describe(
    unit_id="Unique identifier for the unit (e.g., 'FN-INF-001')",
    unit_type="Unit type ID (e.g., 'infantry')",
    owner="Character identifier who will own the unit",
    territory_id="Territory ID where the unit is located"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def create_unit_cmd(interaction: discord.Interaction, unit_id: str, unit_type: str, owner: str, territory_id: int):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.create_unit(conn, unit_id, unit_type, owner, territory_id, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) created unit '{unit_id}' (type: {unit_type}, owner: {owner}, territory: {territory_id}) in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to create unit '{unit_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="delete-unit",
    description="[Admin] Delete a unit"
)
@app_commands.describe(unit_id="The unit ID to delete")
@app_commands.checks.has_permissions(manage_guild=True)
async def delete_unit_cmd(interaction: discord.Interaction, unit_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.delete_unit(conn, unit_id, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) deleted unit '{unit_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to delete unit '{unit_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="set-unit-commander",
    description="[Admin] Assign a commander to a unit"
)
@app_commands.describe(
    unit_id="The unit ID",
    commander="Character identifier for the commander (or 'none' to remove commander)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def set_unit_commander_cmd(interaction: discord.Interaction, unit_id: str, commander: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.set_unit_commander(conn, unit_id, commander, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) set unit '{unit_id}' commander to '{commander}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to set unit '{unit_id}' commander in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


# Resource Management Commands
@tree.command(
    name="modify-resources",
    description="[Admin] Modify a player's resource inventory"
)
@app_commands.describe(character="Character identifier")
@app_commands.checks.has_permissions(manage_guild=True)
async def modify_resources_cmd(interaction: discord.Interaction, character: str):
    async with db_pool.acquire() as conn:
        success, message, data = await handlers.modify_resources(conn, character, interaction.guild_id)

        if not success:
            await interaction.response.send_message(
                emotive_message(message),
                ephemeral=True
            )
            return

        # Show modal
        modal = ModifyResourcesModal(data['character'], data['resources'], db_pool)
        await interaction.response.send_modal(modal)


# Order Management Commands (Player)
@tree.command(
    name="order-join-faction",
    description="Submit an order to join a faction (requires both character and faction leader approval)"
)
@app_commands.describe(
    faction_id="The faction ID to join",
    character_identifier="The identifier of the character that is going to be joining the faction. Assumed to be you if not included."
)
async def order_join_faction_cmd(interaction: discord.Interaction, faction_id: str, character_identifier: Optional[str] = None):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Get character for this user
        character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character in this wargame."),
                ephemeral=True
            )
            return

        if character_identifier is None:
            character_identifier = character.identifier

        success, message = await handlers.submit_join_faction_order(
            conn, character_identifier, faction_id, interaction.guild_id, character.id
        )

        if success:
            logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) submitted join faction order for character '{character_identifier}' to faction '{faction_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"User {interaction.user.name} (ID: {interaction.user.id}) failed to submit join faction order for character '{character_identifier}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="order-leave-faction",
    description="Submit an order to leave your current faction"
)
async def order_leave_faction_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Get character for this user
        character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character in this wargame."),
                ephemeral=True
            )
            return

        success, message = await handlers.submit_leave_faction_order(
            conn, character, interaction.guild_id
        )

        if success:
            logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) submitted leave faction order for character '{character.name}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"User {interaction.user.name} (ID: {interaction.user.id}) failed to submit leave faction order for character '{character.name}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="order-kick-from-faction",
    description="[Faction Leader] Submit an order to kick a member from your faction"
)
@app_commands.describe(
    target_character="Character identifier of the member to kick"
)
async def order_kick_from_faction_cmd(interaction: discord.Interaction, target_character: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Get character for this user
        character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character in this wargame."),
                ephemeral=True
            )
            return

        success, message = await handlers.submit_kick_from_faction_order(
            conn, character, target_character, interaction.guild_id
        )

        if success:
            logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) submitted kick faction order for character '{target_character}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"User {interaction.user.name} (ID: {interaction.user.id}) failed to submit kick faction order for character '{target_character}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="order-transit",
    description="Submit a transit order to move one or more units along a path"
)
@app_commands.describe(
    unit_ids="Comma-separated unit IDs (e.g., 'FN-001' or 'FN-001,FN-002')",
    path="Comma-separated territory IDs for the path (e.g., '101,102,103')"
)
async def order_move_units_cmd(interaction: discord.Interaction, unit_ids: str, path: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Get character for this user
        character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character in this wargame."),
                ephemeral=True
            )
            return

        # Parse unit_ids and path
        unit_id_list = [uid.strip() for uid in unit_ids.split(',')]
        try:
            path_list = [int(tid.strip()) for tid in path.split(',')]
        except ValueError:
            await interaction.followup.send(
                emotive_message("Invalid path format. Please use comma-separated territory IDs (e.g., '101,102,103')."),
                ephemeral=True
            )
            return

        success, message = await handlers.submit_transit_order(
            conn, unit_id_list, path_list, interaction.guild_id, character.id
        )

        if success:
            logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) submitted transit order for units {unit_ids} along path {path} in guild {interaction.guild_id}")
        else:
            logger.warning(f"User {interaction.user.name} (ID: {interaction.user.id}) failed to submit transit order for units {unit_ids} in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="order-assign-commander",
    description="[Unit Owner] Submit an order to assign a new commander to your unit"
)
@app_commands.describe(
    unit_id="The unit ID to assign a new commander to",
    new_commander="Character identifier of the new commander"
)
async def order_assign_commander_cmd(interaction: discord.Interaction, unit_id: str, new_commander: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Get character for this user
        character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character in this wargame."),
                ephemeral=True
            )
            return

        success, message, needs_confirmation = await handlers.submit_assign_commander_order(
            conn, unit_id, new_commander, interaction.guild_id, character.id
        )

        if needs_confirmation:
            # Show confirmation dialog for faction mismatch
            view = AssignCommanderConfirmView(
                unit_id=unit_id,
                new_commander_identifier=new_commander,
                new_commander_name=message.split("**")[1] if "**" in message else new_commander,
                warning_message=message,
                db_pool=db_pool,
                guild_id=interaction.guild_id,
                submitting_character_id=character.id
            )
            await interaction.followup.send(message, view=view, ephemeral=True)
            return

        if success:
            logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) submitted assign commander order for unit '{unit_id}' to '{new_commander}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"User {interaction.user.name} (ID: {interaction.user.id}) failed to submit assign commander order for unit '{unit_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="order-resource-transfer",
    description="Submit a one-time resource transfer order"
)
@app_commands.describe(
    recipient="Character identifier to send resources to",
    ore="Amount of ore to transfer (default: 0)",
    lumber="Amount of lumber to transfer (default: 0)",
    coal="Amount of coal to transfer (default: 0)",
    rations="Amount of rations to transfer (default: 0)",
    cloth="Amount of cloth to transfer (default: 0)"
)
async def order_resource_transfer_cmd(
    interaction: discord.Interaction,
    recipient: str,
    ore: int = 0,
    lumber: int = 0,
    coal: int = 0,
    rations: int = 0,
    cloth: int = 0
):
    await interaction.response.defer()

    # Validate at least one resource
    if ore + lumber + coal + rations + cloth == 0:
        await interaction.followup.send(
            emotive_message("Must transfer at least one resource."),
            ephemeral=True
        )
        return

    async with db_pool.acquire() as conn:
        # Get character for this user
        character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character in this wargame."),
                ephemeral=True
            )
            return

        resources = {
            'ore': ore, 'lumber': lumber, 'coal': coal,
            'rations': rations, 'cloth': cloth
        }

        success, message = await handlers.submit_resource_transfer_order(
            conn, character, recipient, resources,
            is_ongoing=False, term=None, guild_id=interaction.guild_id
        )

        if success:
            logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) submitted resource transfer to '{recipient}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"User {interaction.user.name} (ID: {interaction.user.id}) failed to submit resource transfer: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="order-ongoing-transfer",
    description="Submit an ongoing (recurring) resource transfer order"
)
@app_commands.describe(
    recipient="Character identifier to send resources to",
    ore="Amount of ore per turn (default: 0)",
    lumber="Amount of lumber per turn (default: 0)",
    coal="Amount of coal per turn (default: 0)",
    rations="Amount of rations per turn (default: 0)",
    cloth="Amount of cloth per turn (default: 0)",
    term="Number of turns (leave empty for indefinite)"
)
async def order_ongoing_transfer_cmd(
    interaction: discord.Interaction,
    recipient: str,
    ore: int = 0,
    lumber: int = 0,
    coal: int = 0,
    rations: int = 0,
    cloth: int = 0,
    term: int = None
):
    await interaction.response.defer()

    # Validate at least one resource
    if ore + lumber + coal + rations + cloth == 0:
        await interaction.followup.send(
            emotive_message("Must transfer at least one resource."),
            ephemeral=True
        )
        return

    # Validate term if specified
    if term is not None and term < 2:
        await interaction.followup.send(
            emotive_message("Term must be at least 2 turns if specified."),
            ephemeral=True
        )
        return

    async with db_pool.acquire() as conn:
        # Get character for this user
        character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character in this wargame."),
                ephemeral=True
            )
            return

        resources = {
            'ore': ore, 'lumber': lumber, 'coal': coal,
            'rations': rations, 'cloth': cloth
        }

        success, message = await handlers.submit_resource_transfer_order(
            conn, character, recipient, resources,
            is_ongoing=True, term=term, guild_id=interaction.guild_id
        )

        if success:
            logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) submitted ongoing transfer to '{recipient}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"User {interaction.user.name} (ID: {interaction.user.id}) failed to submit ongoing transfer: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="order-cancel-transfer",
    description="Submit an order to cancel an ongoing resource transfer"
)
@app_commands.describe(
    order_id="The order ID of the ongoing transfer to cancel (e.g., 'ORD-0001')"
)
async def order_cancel_transfer_cmd(interaction: discord.Interaction, order_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Get character for this user
        character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character in this wargame."),
                ephemeral=True
            )
            return

        success, message = await handlers.submit_cancel_transfer_order(
            conn, character, order_id, interaction.guild_id
        )

        if success:
            logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) submitted cancel transfer order for '{order_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"User {interaction.user.name} (ID: {interaction.user.id}) failed to submit cancel transfer order for '{order_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="my-orders",
    description="View your pending and ongoing orders"
)
async def my_orders_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        # Get character for this user
        character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character in this wargame."),
                ephemeral=True
            )
            return

        success, message, orders = await handlers.view_pending_orders(
            conn, character.name, interaction.guild_id
        )

        if not success:
            await interaction.followup.send(
                emotive_message(message),
                ephemeral=True
            )
            return

        # Create embed
        embed = turn_embeds.create_orders_embed(character.name, orders)
        await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(
    name="cancel-order",
    description="Cancel a pending order (cannot cancel ongoing orders)"
)
@app_commands.describe(
    order_id="The order ID to cancel (e.g., 'ORD-0001')"
)
async def cancel_order_cmd(interaction: discord.Interaction, order_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Get character for this user
        character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character in this wargame."),
                ephemeral=True
            )
            return

        success, message = await handlers.cancel_order(
            conn, order_id, interaction.guild_id, character.id
        )

        if success:
            logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) cancelled order '{order_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"User {interaction.user.name} (ID: {interaction.user.id}) failed to cancel order '{order_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


# Turn Management Commands (Admin)
@tree.command(
    name="resolve-turn",
    description="[Admin] Execute turn resolution"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def resolve_turn_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        async with conn.transaction():
            success, message, all_events = await handlers.resolve_turn(conn, interaction.guild_id)

            if not success:
                logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to resolve turn in guild {interaction.guild_id}: {message}")
                await interaction.followup.send(
                    emotive_message(message),
                    ephemeral=True
                )
                return

            # Get wargame config for GM reports channel
            config = await WargameConfig.fetch(conn, interaction.guild_id)
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) resolved turn {config.current_turn} in guild {interaction.guild_id} ({len(all_events)} events)")

            # Generate GM report
            summary = {
                'total_events': len(all_events),
                'beginning_events': len([e for e in all_events if e.phase == 'BEGINNING']),
                'movement_events': len([e for e in all_events if e.phase == 'MOVEMENT']),
                'resource_collection_events': len([e for e in all_events if e.phase == 'RESOURCE_COLLECTION']),
                'upkeep_events': len([e for e in all_events if e.phase == 'UPKEEP'])
            }

            gm_embed = turn_embeds.create_gm_turn_report_embed(
                config.current_turn, all_events, summary
            )

            # Send GM report to reports channel
            if config.gm_reports_channel_id:
                try:
                    reports_channel = client.get_channel(config.gm_reports_channel_id)
                    if reports_channel:
                        await reports_channel.send(embed=gm_embed)
                except Exception as e:
                    logger.error(f"Failed to send GM report to channel: {e}")

            # Send individual reports to each character
            characters = await Character.fetch_all(conn, interaction.guild_id)
            for character in characters:
                if not character.channel_id:
                    continue

                # Filter events relevant to this character using affected_character_ids
                character_events = []
                for event in all_events:
                    event_data = event.event_data or {}
                    affected_ids = event_data.get('affected_character_ids', [])

                    if character.id in affected_ids:
                        character_events.append(event)

                if character_events:
                    try:
                        char_channel = client.get_channel(character.channel_id)
                        if char_channel:
                            char_embed = turn_embeds.create_character_turn_report_embed(
                                character.name, config.current_turn, character_events, character.id
                            )
                            await char_channel.send(embed=char_embed)
                    except Exception as e:
                        logger.error(f"Failed to send report to {character.name}: {e}")

            await interaction.followup.send(
                emotive_message(message),
                ephemeral=False
            )


@tree.command(
    name="turn-status",
    description="[Admin] View current turn status and pending orders"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def turn_status_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        success, message, status_data = await handlers.get_turn_status(conn, interaction.guild_id)

        if not success:
            await interaction.followup.send(
                emotive_message(message),
                ephemeral=True
            )
            return

        embed = turn_embeds.create_turn_status_embed(status_data)
        await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(
    name="set-gm-reports-channel",
    description="[Admin] Set the channel where GM turn reports will be sent"
)
@app_commands.describe(
    channel="The channel for GM reports"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def set_gm_reports_channel_cmd(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Fetch or create wargame config
        config = await WargameConfig.fetch(conn, interaction.guild_id)
        if not config:
            config = WargameConfig(guild_id=interaction.guild_id)

        config.gm_reports_channel_id = channel.id
        await config.upsert(conn)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) set GM reports channel to {channel.id} in guild {interaction.guild_id}")

        await interaction.followup.send(
            emotive_message(f"GM reports channel set to {channel.mention}."),
            ephemeral=False
        )


@tree.command(
    name="turn-report",
    description="View your character's turn report"
)
@app_commands.describe(turn_number="Optional: Specific turn number to view (defaults to most recent)")
async def turn_report_cmd(interaction: discord.Interaction, turn_number: int = None):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.generate_character_report(
            conn,
            interaction.user.id,
            interaction.guild_id,
            turn_number
        )

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create and send embed
        embed = turn_embeds.create_character_turn_report_embed(
            data['character'].name,
            data['turn_number'],
            data['events'],
            data['character'].id
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(
    name="gm-turn-report",
    description="[Admin] View the GM turn report"
)
@app_commands.describe(turn_number="Optional: Specific turn number to view (defaults to most recent)")
@app_commands.checks.has_permissions(manage_guild=True)
async def gm_turn_report_cmd(interaction: discord.Interaction, turn_number: int = None):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.generate_gm_report(
            conn,
            interaction.guild_id,
            turn_number
        )

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create and send embed
        embed = turn_embeds.create_gm_turn_report_embed(
            data['turn_number'],
            data['events'],
            data['summary']
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(
    name="edit-wargame-config",
    description="[Admin] Edit wargame configuration settings"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def edit_wargame_config_cmd(interaction: discord.Interaction):
    async with db_pool.acquire() as conn:
        success, message, config = await handlers.fetch_wargame_config(conn, interaction.guild_id)

        if not success:
            await interaction.response.send_message(
                emotive_message(message),
                ephemeral=True
            )
            return

        # Show modal
        modal = EditWargameConfigModal(config, db_pool, interaction.guild)
        await interaction.response.send_modal(modal)


client.run(BOT_TOKEN)
