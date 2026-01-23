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
    level=logging.DEBUG,
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
async def view_territory_cmd(interaction: discord.Interaction, territory_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_territory(conn, territory_id, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create and send embed
        embed = create_territory_embed(
            data['territory'],
            data['adjacent_ids'],
            data['controller_name'],
            data.get('buildings')
        )
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

        # Determine if user can see spending info
        # (admin, faction leader, or has FINANCIAL permission)
        show_spending = False
        if admin:
            show_spending = True
        else:
            # Check if user's character is leader or has FINANCIAL permission
            character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
            if character:
                faction = data['faction']
                # Check if they are the leader
                if faction.leader_character_id == character.id:
                    show_spending = True
                else:
                    # Check for FINANCIAL permission
                    has_financial = await FactionPermission.has_permission(
                        conn, faction.id, character.id, 'FINANCIAL', interaction.guild_id
                    )
                    if has_financial:
                        show_spending = True

        # Create and send embed
        if admin:
            embed = create_faction_embed(
                data['faction'], data['members'], data['leader'],
                show_spending=show_spending
            )
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
    type_id="The unit type ID to view"
)
async def view_unit_type_cmd(interaction: discord.Interaction, type_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_unit_type(conn, type_id, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create and send embed
        embed = create_unit_type_embed(data['unit_type'])
        await interaction.followup.send(embed=embed)


@tree.command(
    name="view-building-type",
    description="View detailed information about a building type"
)
@app_commands.describe(
    type_id="The building type ID to view"
)
async def view_building_type_cmd(interaction: discord.Interaction, type_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_building_type(conn, type_id, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create and send embed
        embed = create_building_type_embed(data['building_type'])
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
    description="View your character's faction membership(s)"
)
async def my_faction_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_faction_membership(conn, interaction.user.id, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create embed for represented faction
        embed = create_faction_embed(data['faction'], data['members'], data['leader'])

        # Build description with representation info
        description_lines = [f"**Representing:** {data['faction'].name}"]
        description_lines.append(f"Faction ID: `{data['faction'].faction_id}`")

        # Show all memberships if multiple factions
        all_memberships = data.get('all_memberships', [])
        if len(all_memberships) > 1:
            description_lines.append("")
            description_lines.append("**All Memberships:**")
            for m in all_memberships:
                faction = m['faction']
                is_rep = m['is_represented']
                is_leader = m['is_leader']
                markers = []
                if is_rep:
                    markers.append("representing")
                if is_leader:
                    markers.append("leader")
                marker_str = f" ({', '.join(markers)})" if markers else ""
                description_lines.append(f"- {faction.name} (`{faction.faction_id}`) - joined turn {m['joined_turn']}{marker_str}")

        # Show representation change status
        can_change = data.get('can_change_representation', True)
        turns_remaining = data.get('turns_until_change', 0)
        if not can_change and turns_remaining > 0:
            description_lines.append("")
            description_lines.append(f"*Representation change on cooldown: {turns_remaining} turn(s) remaining*")
        elif len(all_memberships) > 1:
            description_lines.append("")
            description_lines.append("*Use `/set-representation` to change represented faction*")

        embed.description = "\n".join(description_lines)
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

        # Create summary embed
        embed = discord.Embed(
            title=f"{data['character'].name}'s Units",
            color=discord.Color.blue()
        )

        # Active owned units
        owned_list = []
        for unit in data['owned_units']:
            unit_str = f"`{unit.unit_id}`: {unit.name or unit.unit_type}"
            if unit.current_territory_id is not None:
                unit_str += f" (Territory {unit.current_territory_id})"
            owned_list.append(unit_str)

        if owned_list:
            embed.add_field(
                name=f"Owned Units ({len(owned_list)})",
                value="\n".join(owned_list),
                inline=False
            )

        # Active commanded units (exclude owned to avoid duplicates)
        owned_ids = {u.id for u in data['owned_units']}
        commanded_list = []
        for unit in data['commanded_units']:
            if unit.id not in owned_ids:
                unit_str = f"`{unit.unit_id}`: {unit.name or unit.unit_type}"
                if unit.current_territory_id is not None:
                    unit_str += f" (Territory {unit.current_territory_id})"
                commanded_list.append(unit_str)

        if commanded_list:
            embed.add_field(
                name=f"Commanded Units ({len(commanded_list)})",
                value="\n".join(commanded_list),
                inline=False
            )

        # Disbanded units section
        disbanded_list = []
        for unit in data['disbanded_units']:
            is_owner = unit.owner_character_id == data['character'].id
            role = "owned" if is_owner else "commanded"
            disbanded_list.append(f"`{unit.unit_id}`: {unit.name or unit.unit_type} ({role})")

        if disbanded_list:
            embed.add_field(
                name=f"Disbanded Units ({len(disbanded_list)})",
                value="\n".join(disbanded_list),
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


@tree.command(
    name="my-finances",
    description="View your character's financial report"
)
async def my_finances_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_character_finances(conn, interaction.user.id, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        embed = create_character_finances_embed(data)
        await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(
    name="my-faction-finances",
    description="View your faction's financial report (requires FINANCIAL permission)"
)
async def my_faction_finances_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_faction_finances(conn, interaction.user.id, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        embed = create_faction_finances_embed(data)
        await interaction.followup.send(embed=embed, ephemeral=True)


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
        await conn.execute("DELETE FROM TurnLog WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM Unit WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM Building WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM BuildingType WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM Territory WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM Alliance WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM WarParticipant WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM War WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM FactionJoinRequest WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM Faction WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", interaction.guild_id)

        # Zero out character production (characters are shared with Hawky, so don't delete them)
        await conn.execute("""
            UPDATE Character
            SET ore_production = 0,
                lumber_production = 0,
                coal_production = 0,
                rations_production = 0,
                cloth_production = 0,
                platinum_production = 0
            WHERE guild_id = $1;
        """, interaction.guild_id)

        logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) cleared all wargame data for guild {interaction.guild_id}")

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
    name="view-finances",
    description="[Admin] View financial report for a character or faction"
)
@app_commands.describe(identifier="Character identifier or faction ID")
@app_commands.checks.has_permissions(manage_guild=True)
async def view_finances_cmd(interaction: discord.Interaction, identifier: str):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.admin_view_finances(conn, identifier, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        entity_type = data.get('entity_type', 'character')
        if entity_type == 'character':
            embed = create_character_finances_embed(data)
        else:
            embed = create_faction_finances_embed(data)

        await interaction.followup.send(embed=embed, ephemeral=True)


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
    name="list-building-types",
    description="[Admin] List all building type IDs in this server"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def list_building_types_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.list_building_types(conn, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message))
            return

        building_type_list = []
        for building_type in data:
            desc_str = f" - {building_type.description[:50]}..." if building_type.description and len(building_type.description) > 50 else (f" - {building_type.description}" if building_type.description else "")
            building_type_list.append(f"`{building_type.type_id}`: {building_type.name}{desc_str}")

        embed = discord.Embed(
            title="🏛️ All Building Types",
            description="\n".join(building_type_list),
            color=discord.Color.dark_teal()
        )
        embed.set_footer(text=f"Total: {len(data)} building types")

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
    leader="Optional: Character identifier for the faction leader",
    nation="Optional: Nation identifier (e.g., 'fire-nation', 'earth-kingdom')"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def create_faction_cmd(interaction: discord.Interaction, faction_id: str, name: str, leader: str = None, nation: str = None):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.create_faction(conn, faction_id, name, interaction.guild_id, leader, nation)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) created faction '{faction_id}' (name: {name}, leader: {leader}, nation: {nation}) in guild {interaction.guild_id}")
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
    name="set-faction-nation",
    description="[Admin] Set or update a faction's nation"
)
@app_commands.describe(
    faction_id="The faction ID",
    nation="Nation identifier (e.g., 'fire-nation', 'earth-kingdom', 'fifth-nation')"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def set_faction_nation_cmd(interaction: discord.Interaction, faction_id: str, nation: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.set_faction_nation(conn, faction_id, nation, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) set nation for faction '{faction_id}' to '{nation}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to set nation for faction '{faction_id}' in guild {interaction.guild_id}: {message}")

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
    description="[Admin] Remove a member from a faction"
)
@app_commands.describe(
    character="Character identifier to remove",
    faction_id="Faction ID to remove from. If not specified, removes from represented faction."
)
@app_commands.checks.has_permissions(manage_guild=True)
async def remove_faction_member_cmd(interaction: discord.Interaction, character: str, faction_id: str = None):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.remove_faction_member(conn, character, interaction.guild_id, faction_id=faction_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) removed character '{character}' from faction in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to remove character '{character}' from faction in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="set-representation",
    description="Change which faction you publicly represent (3-turn cooldown)"
)
@app_commands.describe(faction_id="The faction ID to represent")
async def set_representation_cmd(interaction: discord.Interaction, faction_id: str):
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

        success, message = await handlers.set_character_representation(
            conn, character.id, faction_id, interaction.guild_id
        )

        if success:
            logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) changed representation to '{faction_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"User {interaction.user.name} (ID: {interaction.user.id}) failed to change representation to '{faction_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=True
        )


@tree.command(
    name="admin-set-representation",
    description="[Admin] Force-set a character's representation (bypasses cooldown)"
)
@app_commands.describe(
    character="Character identifier",
    faction_id="Faction ID to represent"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def admin_set_representation_cmd(interaction: discord.Interaction, character: str, faction_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.admin_set_character_representation(
            conn, character, faction_id, interaction.guild_id
        )

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) set character '{character}' to represent '{faction_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to set character '{character}' representation to '{faction_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="grant-faction-permission",
    description="[Admin] Grant a faction permission to a character"
)
@app_commands.describe(
    faction_id="The faction ID",
    character="Character identifier to grant permission to",
    permission_type="Permission type (COMMAND, FINANCIAL, MEMBERSHIP, CONSTRUCTION)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def grant_faction_permission_cmd(
    interaction: discord.Interaction,
    faction_id: str,
    character: str,
    permission_type: str
):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.grant_faction_permission(
            conn, faction_id, character, permission_type, interaction.guild_id
        )

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) granted {permission_type} permission to '{character}' for faction '{faction_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to grant permission in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="revoke-faction-permission",
    description="[Admin] Revoke a faction permission from a character"
)
@app_commands.describe(
    faction_id="The faction ID",
    character="Character identifier to revoke permission from",
    permission_type="Permission type (COMMAND, FINANCIAL, MEMBERSHIP, CONSTRUCTION)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def revoke_faction_permission_cmd(
    interaction: discord.Interaction,
    faction_id: str,
    character: str,
    permission_type: str
):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.revoke_faction_permission(
            conn, faction_id, character, permission_type, interaction.guild_id
        )

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) revoked {permission_type} permission from '{character}' for faction '{faction_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to revoke permission in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="view-faction-permissions",
    description="[Admin] View all permissions for a faction"
)
@app_commands.describe(faction_id="The faction ID")
@app_commands.checks.has_permissions(manage_guild=True)
async def view_faction_permissions_cmd(interaction: discord.Interaction, faction_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.get_faction_permissions(
            conn, faction_id, interaction.guild_id
        )

        if not success:
            await interaction.followup.send(
                emotive_message(message),
                ephemeral=True
            )
            return

        if not data:
            await interaction.followup.send(
                f"No permissions found for faction '{faction_id}'.",
                ephemeral=True
            )
            return

        # Build response showing permissions by character
        response_lines = [f"**Faction Permissions: {faction_id}**\n"]
        for perm in data:
            response_lines.append(f"- {perm['character_name']}: {perm['permission_type']}")

        await interaction.followup.send("\n".join(response_lines), ephemeral=True)


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
async def create_territory_cmd(interaction: discord.Interaction, territory_id: str, terrain_type: str, name: str = None):
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
async def edit_territory_cmd(interaction: discord.Interaction, territory_id: str):
    async with db_pool.acquire() as conn:
        # Fetch territory for modal (don't edit it yet)
        territory = await Territory.fetch_by_territory_id(conn, territory_id, interaction.guild_id)

        if not territory:
            await interaction.response.send_message(
                emotive_message(f"Territory {territory_id} not found."),
                ephemeral=True
            )
            return

        # Show modal with existing values pre-populated
        modal = EditTerritoryModal(territory, db_pool)
        await interaction.response.send_modal(modal)


@tree.command(
    name="delete-territory",
    description="[Admin] Delete a territory"
)
@app_commands.describe(territory_id="The territory ID to delete")
@app_commands.checks.has_permissions(manage_guild=True)
async def delete_territory_cmd(interaction: discord.Interaction, territory_id: str):
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
    description="[Admin] Change the controller of a territory (character or faction)"
)
@app_commands.describe(
    territory_id="The territory ID",
    character="Character identifier to control the territory (or 'none' for uncontrolled)",
    faction="Faction ID to control the territory (mutually exclusive with character)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def set_territory_controller_cmd(
    interaction: discord.Interaction,
    territory_id: str,
    character: str = None,
    faction: str = None
):
    await interaction.response.defer()

    # Validate mutually exclusive parameters
    if character and faction:
        await interaction.followup.send(
            emotive_message("Cannot specify both character and faction. Choose one."),
            ephemeral=True
        )
        return

    if not character and not faction:
        await interaction.followup.send(
            emotive_message("Must specify either character or faction (use 'none' to remove controller)."),
            ephemeral=True
        )
        return

    # Determine controller type and identifier
    if character:
        controller_identifier = character
        controller_type = 'character'
    else:
        controller_identifier = faction
        controller_type = 'faction'

    async with db_pool.acquire() as conn:
        success, message = await handlers.set_territory_controller(
            conn, territory_id, controller_identifier, interaction.guild_id, controller_type
        )

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) set territory {territory_id} controller to '{controller_identifier}' ({controller_type}) in guild {interaction.guild_id}")
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
async def add_adjacency_cmd(interaction: discord.Interaction, territory_id_1: str, territory_id_2: str):
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
async def remove_adjacency_cmd(interaction: discord.Interaction, territory_id_1: str, territory_id_2: str):
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
    name="Display name for the unit type"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def create_unit_type_cmd(interaction: discord.Interaction, type_id: str, name: str):
    async with db_pool.acquire() as conn:
        success, message, data = await handlers.create_unit_type(conn, type_id, name, interaction.guild_id)

        if not success:
            await interaction.response.send_message(
                emotive_message(message),
                ephemeral=True
            )
            return

        # Show modal for stats/costs (nation can be set in the modal)
        modal = EditUnitTypeModal(unit_type=None, type_id=data['type_id'], name=data['name'], db_pool=db_pool)
        await interaction.response.send_modal(modal)


@tree.command(
    name="edit-unit-type",
    description="[Admin] Edit unit type properties"
)
@app_commands.describe(
    type_id="The unit type ID to edit"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def edit_unit_type_cmd(interaction: discord.Interaction, type_id: str):
    async with db_pool.acquire() as conn:
        success, message, unit_type = await handlers.edit_unit_type(conn, type_id, interaction.guild_id)

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
    type_id="The unit type ID to delete"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def delete_unit_type_cmd(interaction: discord.Interaction, type_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.delete_unit_type(conn, type_id, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) deleted unit type '{type_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to delete unit type '{type_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


# Building Type Management Commands
@tree.command(
    name="create-building-type",
    description="[Admin] Create a new building type"
)
@app_commands.describe(
    type_id="Unique identifier for the building type (e.g., 'barracks')",
    name="Display name for the building type"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def create_building_type_cmd(interaction: discord.Interaction, type_id: str, name: str):
    async with db_pool.acquire() as conn:
        success, message, data = await handlers.create_building_type(conn, type_id, name, interaction.guild_id)

        if not success:
            await interaction.response.send_message(
                emotive_message(message),
                ephemeral=True
            )
            return

        # Show modal for description/costs
        modal = EditBuildingTypeModal(building_type=None, type_id=data['type_id'], name=data['name'], db_pool=db_pool)
        await interaction.response.send_modal(modal)


@tree.command(
    name="edit-building-type",
    description="[Admin] Edit building type properties"
)
@app_commands.describe(
    type_id="The building type ID to edit"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def edit_building_type_cmd(interaction: discord.Interaction, type_id: str):
    async with db_pool.acquire() as conn:
        success, message, building_type = await handlers.edit_building_type(conn, type_id, interaction.guild_id)

        if not success:
            await interaction.response.send_message(
                emotive_message(message),
                ephemeral=True
            )
            return

        # Show modal
        modal = EditBuildingTypeModal(building_type=building_type, db_pool=db_pool)
        await interaction.response.send_modal(modal)


@tree.command(
    name="delete-building-type",
    description="[Admin] Delete a building type"
)
@app_commands.describe(
    type_id="The building type ID to delete"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def delete_building_type_cmd(interaction: discord.Interaction, type_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.delete_building_type(conn, type_id, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) deleted building type '{type_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to delete building type '{type_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


# Building Commands
@tree.command(
    name="view-building",
    description="View detailed information about a building"
)
@app_commands.describe(building_id="The building ID to view")
async def view_building_cmd(interaction: discord.Interaction, building_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_building(conn, building_id, interaction.guild_id)

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create and send embed
        embed = create_building_embed(
            data['building'],
            data.get('building_type'),
            data.get('territory')
        )
        await interaction.followup.send(embed=embed)


@tree.command(
    name="create-building",
    description="[Admin] Create a new building in a territory"
)
@app_commands.describe(
    building_id="Unique identifier for the building (e.g., 'fire-barracks')",
    building_type="Building type ID (e.g., 'barracks')",
    territory_id="Territory ID where the building will be located",
    name="Optional custom name for the building"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def create_building_cmd(
    interaction: discord.Interaction,
    building_id: str,
    building_type: str,
    territory_id: str,
    name: str = None
):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.create_building(
            conn, building_id, building_type, territory_id, interaction.guild_id, name
        )

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) created building '{building_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to create building '{building_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="edit-building",
    description="[Admin] Edit a building's properties"
)
@app_commands.describe(
    building_id="The building ID to edit",
    name="New name for the building (optional)",
    durability="New durability value (optional)",
    status="New status: ACTIVE or DESTROYED (optional)",
    keywords="Keywords (comma-separated, optional)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def edit_building_cmd(
    interaction: discord.Interaction,
    building_id: str,
    name: str = None,
    durability: int = None,
    status: str = None,
    keywords: str = None
):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.edit_building(
            conn, building_id, interaction.guild_id, name, durability, status, keywords
        )

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited building '{building_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to edit building '{building_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="delete-building",
    description="[Admin] Delete a building"
)
@app_commands.describe(
    building_id="The building ID to delete"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def delete_building_cmd(interaction: discord.Interaction, building_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.delete_building(conn, building_id, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) deleted building '{building_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to delete building '{building_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


# Unit Management Commands
@tree.command(
    name="create-unit",
    description="[Admin] Create a new unit (owned by character or faction)"
)
@app_commands.describe(
    unit_id="Unique identifier for the unit (e.g., 'FN-INF-001')",
    unit_type="Unit type ID (e.g., 'infantry')",
    territory_id="Territory ID where the unit is located",
    owner="Character identifier who will own the unit (mutually exclusive with owner_faction)",
    owner_faction="Faction ID that will own the unit (mutually exclusive with owner)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def create_unit_cmd(
    interaction: discord.Interaction,
    unit_id: str,
    unit_type: str,
    territory_id: str,
    owner: str = None,
    owner_faction: str = None
):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.create_unit(
            conn=conn,
            unit_id=unit_id,
            unit_type=unit_type,
            territory_id=territory_id,
            guild_id=interaction.guild_id,
            owner_character=owner,
            owner_faction=owner_faction
        )

        owner_info = owner if owner else f"faction:{owner_faction}"
        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) created unit '{unit_id}' (type: {unit_type}, owner: {owner_info}, territory: {territory_id}) in guild {interaction.guild_id}")
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


@tree.command(
    name="set-unit-status",
    description="[Admin] Set a unit's status (ACTIVE or DISBANDED)"
)
@app_commands.describe(
    unit_id="The unit ID",
    status="New status: ACTIVE or DISBANDED"
)
@app_commands.choices(status=[
    app_commands.Choice(name="ACTIVE", value="ACTIVE"),
    app_commands.Choice(name="DISBANDED", value="DISBANDED"),
])
@app_commands.checks.has_permissions(manage_guild=True)
async def set_unit_status_cmd(interaction: discord.Interaction, unit_id: str, status: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.set_unit_status(conn, unit_id, status, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) set unit '{unit_id}' status to '{status}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to set unit '{unit_id}' status in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="edit-unit",
    description="[Admin] Edit a unit's properties"
)
@app_commands.describe(unit_id="The unit ID to edit")
@app_commands.checks.has_permissions(manage_guild=True)
async def edit_unit_cmd(interaction: discord.Interaction, unit_id: str):
    async with db_pool.acquire() as conn:
        success, message, unit = await handlers.get_unit_for_edit(conn, unit_id, interaction.guild_id)

        if not success:
            await interaction.response.send_message(
                emotive_message(message),
                ephemeral=True
            )
            return

        embed = create_edit_unit_embed(unit)
        view = EditUnitView(unit, db_pool)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


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

        # Show embed with resource buttons
        embed = create_modify_resources_embed(data['character'], data['resources'])
        view = ModifyResourcesView(data['character'], data['resources'], db_pool)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@tree.command(
    name="modify-character-production",
    description="[Admin] Modify a character's resource production values"
)
@app_commands.describe(character="Character identifier")
@app_commands.checks.has_permissions(manage_guild=True)
async def modify_character_production_cmd(interaction: discord.Interaction, character: str):
    async with db_pool.acquire() as conn:
        success, message, data = await handlers.modify_character_production(conn, character, interaction.guild_id)

        if not success:
            await interaction.response.send_message(
                emotive_message(message),
                ephemeral=True
            )
            return

        # Show embed with production buttons
        embed = create_modify_character_production_embed(data['character'])
        view = ModifyCharacterProductionView(data['character'], db_pool)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@tree.command(
    name="modify-character-vp",
    description="[Admin] Modify a character's victory points"
)
@app_commands.describe(character="Character identifier")
@app_commands.checks.has_permissions(manage_guild=True)
async def modify_character_vp_cmd(interaction: discord.Interaction, character: str):
    async with db_pool.acquire() as conn:
        success, message, data = await handlers.modify_character_vp(conn, character, interaction.guild_id)

        if not success:
            await interaction.response.send_message(
                emotive_message(message),
                ephemeral=True
            )
            return

        # Show VP modification modal
        modal = ModifyCharacterVPModal(data['character'], db_pool)
        await interaction.response.send_modal(modal)


@tree.command(
    name="view-faction-resources",
    description="[Admin] View a faction's resource stockpile"
)
@app_commands.describe(faction_id="Faction ID to view resources for")
@app_commands.checks.has_permissions(manage_guild=True)
async def view_faction_resources_cmd(interaction: discord.Interaction, faction_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.get_faction_resources(conn, faction_id, interaction.guild_id)

        if not success:
            await interaction.followup.send(
                emotive_message(message),
                ephemeral=True
            )
            return

        # Build response message
        response = f"**{data['faction_name']} Resources**\n"
        response += f"Ore: {data['ore']}\n"
        response += f"Lumber: {data['lumber']}\n"
        response += f"Coal: {data['coal']}\n"
        response += f"Rations: {data['rations']}\n"
        response += f"Cloth: {data['cloth']}\n"
        response += f"Platinum: {data['platinum']}"

        await interaction.followup.send(response, ephemeral=True)


@tree.command(
    name="modify-faction-resources",
    description="[Admin] Modify a faction's resource stockpile"
)
@app_commands.describe(
    faction_id="Faction ID to modify",
    ore="Change in ore (can be negative)",
    lumber="Change in lumber (can be negative)",
    coal="Change in coal (can be negative)",
    rations="Change in rations (can be negative)",
    cloth="Change in cloth (can be negative)",
    platinum="Change in platinum (can be negative)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def modify_faction_resources_cmd(
    interaction: discord.Interaction,
    faction_id: str,
    ore: int = 0,
    lumber: int = 0,
    coal: int = 0,
    rations: int = 0,
    cloth: int = 0,
    platinum: int = 0
):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        changes = {
            'ore': ore,
            'lumber': lumber,
            'coal': coal,
            'rations': rations,
            'cloth': cloth,
            'platinum': platinum
        }

        success, message = await handlers.modify_faction_resources(conn, faction_id, interaction.guild_id, changes)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) modified resources for faction '{faction_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to modify faction resources for '{faction_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="edit-faction-spending",
    description="[Admin] Edit a faction's per-turn resource spending"
)
@app_commands.describe(
    faction_id="Faction ID to edit",
    ore="Ore spent per turn (only updates if provided)",
    lumber="Lumber spent per turn (only updates if provided)",
    coal="Coal spent per turn (only updates if provided)",
    rations="Rations spent per turn (only updates if provided)",
    cloth="Cloth spent per turn (only updates if provided)",
    platinum="Platinum spent per turn (only updates if provided)"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def edit_faction_spending_cmd(
    interaction: discord.Interaction,
    faction_id: str,
    ore: Optional[int] = None,
    lumber: Optional[int] = None,
    coal: Optional[int] = None,
    rations: Optional[int] = None,
    cloth: Optional[int] = None,
    platinum: Optional[int] = None
):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Only include values that were explicitly provided
        spending = {}
        if ore is not None:
            spending['ore'] = ore
        if lumber is not None:
            spending['lumber'] = lumber
        if coal is not None:
            spending['coal'] = coal
        if rations is not None:
            spending['rations'] = rations
        if cloth is not None:
            spending['cloth'] = cloth
        if platinum is not None:
            spending['platinum'] = platinum

        success, message = await handlers.edit_faction_spending(conn, faction_id, interaction.guild_id, spending)

        if success:
            logger.info(f"Admin {interaction.user.name} (ID: {interaction.user.id}) edited spending for faction '{faction_id}' in guild {interaction.guild_id}")
        else:
            logger.warning(f"Admin {interaction.user.name} (ID: {interaction.user.id}) failed to edit faction spending for '{faction_id}' in guild {interaction.guild_id}: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="view-faction-spending",
    description="View a faction's per-turn resource spending configuration"
)
@app_commands.describe(faction_id="Faction ID to view spending for")
async def view_faction_spending_cmd(interaction: discord.Interaction, faction_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        admin = is_admin(interaction)

        # Get user's character to check faction membership (if not admin)
        character_id = None
        if not admin:
            character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
            if character:
                character_id = character.id

        success, message, data = await handlers.get_faction_spending(
            conn, faction_id, interaction.guild_id, character_id if not admin else None
        )

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Build response
        response = f"**{data['faction_name']} Spending (per turn)**\n"
        response += f"Ore: {data['ore']}\n"
        response += f"Lumber: {data['lumber']}\n"
        response += f"Coal: {data['coal']}\n"
        response += f"Rations: {data['rations']}\n"
        response += f"Cloth: {data['cloth']}\n"
        response += f"Platinum: {data['platinum']}\n"

        await interaction.followup.send(response)


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
    description="Submit an order to leave a faction"
)
@app_commands.describe(
    faction_id="Faction ID to leave. If not specified, leaves your represented faction."
)
async def order_leave_faction_cmd(interaction: discord.Interaction, faction_id: str = None):
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
            conn, character, interaction.guild_id, faction_id=faction_id
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


# Define action choices for /order-unit command
UNIT_ACTION_CHOICES = [
    app_commands.Choice(name="Transit (land)", value="transit"),
    app_commands.Choice(name="Transport (land)", value="transport"),
    app_commands.Choice(name="Patrol (land)", value="patrol"),
    app_commands.Choice(name="Raid", value="raid"),
    app_commands.Choice(name="Capture", value="capture"),
    app_commands.Choice(name="Siege", value="siege"),
    app_commands.Choice(name="Aerial Convoy", value="aerial_convoy"),
    app_commands.Choice(name="Naval Transit", value="naval_transit"),
    app_commands.Choice(name="Naval Convoy", value="naval_convoy"),
    app_commands.Choice(name="Naval Patrol", value="naval_patrol"),
    app_commands.Choice(name="Naval Transport", value="naval_transport"),
]


@tree.command(
    name="order-unit",
    description="[Unit Commander] Submit a unit order (transit, patrol, raid, capture, siege, etc.)"
)
@app_commands.describe(
    unit_ids="Comma-separated unit IDs (e.g., 'FN-001' or 'FN-001,FN-002')",
    action="The action type for this order",
    path="Comma-separated territory IDs for the path (e.g., '101,102,103')",
    speed="Speed parameter for patrol orders only (optional)"
)
@app_commands.choices(action=UNIT_ACTION_CHOICES)
async def order_unit_cmd(
    interaction: discord.Interaction,
    unit_ids: str,
    action: app_commands.Choice[str],
    path: str,
    speed: int = None
):
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
        path_list = [tid.strip() for tid in path.split(',')]

        # Validate path is not empty
        if not path_list or not path_list[0]:
            await interaction.followup.send(
                emotive_message("Invalid path format. Please use comma-separated territory IDs (e.g., '101,102,103')."),
                ephemeral=True
            )
            return

        success, message, extra_data = await handlers.submit_unit_order(
            conn, unit_id_list, action.value, path_list, interaction.guild_id, character.id, speed=speed
        )

        if extra_data and extra_data.get('confirmation_needed'):
            # Show confirmation dialog for existing orders
            existing_orders = extra_data.get('existing_orders', [])
            order_details = []
            for order in existing_orders:
                order_details.append(
                    f"- Order #{order['order_id']} ({order['order_type']}, {order['status']}): units {', '.join(order['affected_units'])}"
                )
            warning_msg = f"The following units have existing orders that will be cancelled:\n" + "\n".join(order_details)

            view = UnitOrderConfirmView(
                unit_ids=unit_id_list,
                action=action.value,
                path=path_list,
                speed=speed,
                existing_orders=existing_orders,
                db_pool=db_pool,
                guild_id=interaction.guild_id,
                submitting_character_id=character.id
            )
            await interaction.followup.send(warning_msg, view=view, ephemeral=True)
            return

        if success:
            logger.info(f"User {interaction.user.name} (ID: {interaction.user.id}) submitted unit order ({action.value}) for units {unit_ids} along path {path} in guild {interaction.guild_id}")
        else:
            logger.warning(f"User {interaction.user.name} (ID: {interaction.user.id}) failed to submit unit order ({action.value}) for units {unit_ids} in guild {interaction.guild_id}: {message}")

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
    cloth="Amount of cloth to transfer (default: 0)",
    platinum="Amount of platinum to transfer (default: 0)"
)
async def order_resource_transfer_cmd(
    interaction: discord.Interaction,
    recipient: str,
    ore: int = 0,
    lumber: int = 0,
    coal: int = 0,
    rations: int = 0,
    cloth: int = 0,
    platinum: int = 0
):
    await interaction.response.defer()

    # Validate at least one resource
    if ore + lumber + coal + rations + cloth + platinum == 0:
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
            'rations': rations, 'cloth': cloth, 'platinum': platinum
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
    platinum="Amount of platinum per turn (default: 0)",
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
    platinum: int = 0,
    term: int = None
):
    await interaction.response.defer()

    # Validate at least one resource
    if ore + lumber + coal + rations + cloth + platinum == 0:
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
            'rations': rations, 'cloth': cloth, 'platinum': platinum
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

            # Generate and send GM report using the same function as gm-turn-report
            gm_success, _, gm_data = await handlers.generate_gm_report(
                conn, interaction.guild_id, config.current_turn
            )
            if gm_success and config.gm_reports_channel_id:
                try:
                    reports_channel = client.get_channel(config.gm_reports_channel_id)
                    if reports_channel:
                        gm_embeds = turn_embeds.create_gm_turn_report_embeds(
                            gm_data['turn_number'],
                            gm_data['events'],
                            gm_data['summary']
                        )
                        for embed in gm_embeds:
                            await reports_channel.send(embed=embed)
                except Exception as e:
                    logger.error(f"Failed to send GM report to channel: {e}")

            # Send individual reports to each character using the same function as turn-report
            characters = await Character.fetch_all(conn, interaction.guild_id)
            for character in characters:
                logger.info(f"Sending report to character: {character.identifier}")
                if not character.channel_id:
                    logger.warn(f"Character {character.identifier} has no channel defined")
                    continue

                # Use generate_character_report to get filtered events for this character
                char_success, _, char_data = await handlers.generate_character_report(
                    conn, character, interaction.guild_id, config.current_turn
                )

                if char_success and char_data['events']:
                    try:
                        char_channel = client.get_channel(character.channel_id)
                        if char_channel:
                            char_embeds = turn_embeds.create_character_turn_report_embeds(
                                char_data['character'].name,
                                char_data['turn_number'],
                                char_data['events'],
                                char_data['character'].id
                            )
                            for embed in char_embeds:
                                await char_channel.send(embed=embed)
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
        # Look up the character for this user
        character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character in this wargame."),
                ephemeral=True
            )
            return

        # Get wargame config for turn number
        config = await WargameConfig.fetch(conn, interaction.guild_id)
        if not config:
            await interaction.followup.send(
                emotive_message("No wargame configuration found for this server."),
                ephemeral=True
            )
            return

        # Determine and validate turn number
        report_turn = turn_number if turn_number is not None else config.current_turn
        if report_turn < 0 or report_turn > config.current_turn:
            await interaction.followup.send(
                emotive_message(f"Invalid turn number. Must be between 0 and {config.current_turn}."),
                ephemeral=True
            )
            return

        success, message, data = await handlers.generate_character_report(
            conn, character, interaction.guild_id, report_turn
        )

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create and send embeds
        embeds = turn_embeds.create_character_turn_report_embeds(
            data['character'].name,
            data['turn_number'],
            data['events'],
            data['character'].id
        )
        for embed in embeds:
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

        # Create and send embeds
        embeds = turn_embeds.create_gm_turn_report_embeds(
            data['turn_number'],
            data['events'],
            data['summary']
        )
        for embed in embeds:
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


@tree.command(
    name="my-victory-points",
    description="View your victory points and faction VP totals"
)
async def my_victory_points_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_victory_points(
            conn, interaction.user.id, interaction.guild_id
        )

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create and send embed
        embed = create_victory_points_embed(data)
        await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(
    name="view-victory-points",
    description="[Admin] View victory points for a faction"
)
@app_commands.describe(
    faction_id="The faction ID to view"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def view_victory_points_cmd(interaction: discord.Interaction, faction_id: str):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        success, message, data = await handlers.view_faction_victory_points(
            conn, faction_id, interaction.guild_id
        )

        if not success:
            await interaction.followup.send(emotive_message(message), ephemeral=True)
            return

        # Create and send embed
        embed = create_faction_victory_points_embed(data)
        await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(
    name="order-assign-vp",
    description="Submit an order to assign your victory points to a faction"
)
@app_commands.describe(
    faction_id="The faction ID to assign your VPs to"
)
async def order_assign_vp_cmd(interaction: discord.Interaction, faction_id: str):
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

        success, message = await handlers.submit_assign_victory_points_order(
            conn, character, faction_id, interaction.guild_id
        )

        if success:
            logger.info(f"User {interaction.user.name} submitted VP assignment to '{faction_id}'")
        else:
            logger.warning(f"User {interaction.user.name} failed VP assignment: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


# ============================================================================
# ALLIANCE COMMANDS
# ============================================================================

@tree.command(
    name="order-make-alliance",
    description="[Faction Leader] Submit an order to form an alliance with another faction"
)
@app_commands.describe(
    target_faction_id="The faction ID to form an alliance with"
)
async def order_make_alliance_cmd(interaction: discord.Interaction, target_faction_id: str):
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

        success, message = await handlers.submit_make_alliance_order(
            conn, character, target_faction_id, interaction.guild_id
        )

        if success:
            logger.info(f"User {interaction.user.name} submitted alliance order for '{target_faction_id}'")
        else:
            logger.warning(f"User {interaction.user.name} failed alliance order: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="order-dissolve-alliance",
    description="[Faction Leader] Submit an order to dissolve an alliance with another faction"
)
@app_commands.describe(
    target_faction_id="The faction ID of the alliance to dissolve"
)
async def order_dissolve_alliance_cmd(interaction: discord.Interaction, target_faction_id: str):
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

        success, message = await handlers.submit_dissolve_alliance_order(
            conn, character, target_faction_id, interaction.guild_id
        )

        if success:
            logger.info(f"User {interaction.user.name} submitted dissolve alliance order for '{target_faction_id}'")
        else:
            logger.warning(f"User {interaction.user.name} failed dissolve alliance order: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="view-alliances",
    description="View alliances in this wargame"
)
async def view_alliances_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Determine viewer's permission level
        is_admin_user = is_admin(interaction)

        # Check if user is a faction leader
        faction_leader_of_id = None
        character = await Character.fetch_by_user(conn, interaction.user.id, interaction.guild_id)
        if character:
            faction_member = await FactionMember.fetch_by_character(conn, character.id, interaction.guild_id)
            if faction_member:
                faction = await Faction.fetch_by_id(conn, faction_member.faction_id)
                if faction and faction.leader_character_id == character.id:
                    faction_leader_of_id = faction.id

        success, message, alliances = await handlers.view_alliances(
            conn, interaction.guild_id, is_admin_user, faction_leader_of_id
        )

        if not success or not alliances:
            await interaction.followup.send(
                emotive_message(message),
                ephemeral=True
            )
            return

        # Build embed
        embed = discord.Embed(
            title="Alliances",
            color=discord.Color.gold()
        )

        for alliance in alliances:
            status_emoji = "🤝" if alliance['status'] == 'ACTIVE' else "⏳"
            field_name = f"{status_emoji} {alliance['faction_a_name']} ↔ {alliance['faction_b_name']}"

            if alliance['status'] == 'ACTIVE':
                field_value = f"Status: Active"
                if alliance.get('activated_at'):
                    field_value += f"\nActivated: {alliance['activated_at'][:10]}"
            else:
                field_value = f"Status: Pending"
                if alliance.get('waiting_for'):
                    field_value += f"\nWaiting for: {alliance['waiting_for']}"
                if alliance.get('initiated_by'):
                    field_value += f"\nInitiated by: {alliance['initiated_by']}"

            embed.add_field(name=field_name, value=field_value, inline=False)

        await interaction.followup.send(embed=embed)


@tree.command(
    name="add-alliance",
    description="[Admin] Create an active alliance between two factions"
)
@app_commands.describe(
    faction_a_id="First faction ID",
    faction_b_id="Second faction ID"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def add_alliance_cmd(interaction: discord.Interaction, faction_a_id: str, faction_b_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.add_alliance(
            conn, faction_a_id, faction_b_id, interaction.guild_id
        )

        if success:
            logger.info(f"Admin {interaction.user.name} created alliance between '{faction_a_id}' and '{faction_b_id}'")
        else:
            logger.warning(f"Admin {interaction.user.name} failed to create alliance: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="edit-alliance",
    description="[Admin] Edit an alliance between two factions"
)
@app_commands.describe(
    faction_a_id="First faction ID",
    faction_b_id="Second faction ID",
    status="New status: PENDING_FACTION_A, PENDING_FACTION_B, or ACTIVE"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def edit_alliance_cmd(interaction: discord.Interaction, faction_a_id: str, faction_b_id: str, status: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.edit_alliance(
            conn, faction_a_id, faction_b_id, status, interaction.guild_id
        )

        if success:
            logger.info(f"Admin {interaction.user.name} edited alliance ({faction_a_id} ↔ {faction_b_id}) to status '{status}'")
        else:
            logger.warning(f"Admin {interaction.user.name} failed to edit alliance: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="delete-alliance",
    description="[Admin] Delete an alliance between two factions"
)
@app_commands.describe(
    faction_a_id="First faction ID",
    faction_b_id="Second faction ID"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def delete_alliance_cmd(interaction: discord.Interaction, faction_a_id: str, faction_b_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.delete_alliance(
            conn, faction_a_id, faction_b_id, interaction.guild_id
        )

        if success:
            logger.info(f"Admin {interaction.user.name} deleted alliance between '{faction_a_id}' and '{faction_b_id}'")
        else:
            logger.warning(f"Admin {interaction.user.name} failed to delete alliance: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


# ============================================================================
# WAR COMMANDS
# ============================================================================

@tree.command(
    name="order-declare-war",
    description="[Faction Leader] Declare war on one or more factions"
)
@app_commands.describe(
    target_faction_ids="Comma-separated faction IDs to declare war on",
    objective="The objective/reason for the war"
)
async def order_declare_war_cmd(interaction: discord.Interaction, target_faction_ids: str, objective: str):
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

        # Parse target faction IDs
        target_ids = [tid.strip() for tid in target_faction_ids.split(',') if tid.strip()]

        if not target_ids:
            await interaction.followup.send(
                emotive_message("You must specify at least one target faction."),
                ephemeral=True
            )
            return

        success, message = await handlers.submit_declare_war_order(
            conn, character, target_ids, objective, interaction.guild_id
        )

        if success:
            logger.info(f"User {interaction.user.name} submitted declare war order targeting '{target_faction_ids}' with objective '{objective}'")
        else:
            logger.warning(f"User {interaction.user.name} failed to submit declare war order: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="order-mobilize",
    description="Submit a mobilization order to create a new unit"
)
@app_commands.describe(
    unit_type="The unit type ID to mobilize (e.g., 'infantry', 'cavalry')",
    territory_id="The territory ID where the unit will be created",
    faction_id="Optional: Faction ID to use faction resources (requires CONSTRUCTION permission)",
    unit_name="Optional: Custom name for the unit"
)
async def order_mobilize_cmd(
    interaction: discord.Interaction,
    unit_type: str,
    territory_id: str,
    faction_id: str = None,
    unit_name: str = None
):
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

        success, message = await handlers.submit_mobilization_order(
            conn, unit_type, territory_id, interaction.guild_id, character.id,
            faction_id=faction_id, unit_name=unit_name
        )

        if success:
            logger.info(f"User {interaction.user.name} submitted mobilization order for {unit_type} in territory {territory_id}")
        else:
            logger.warning(f"User {interaction.user.name} failed to submit mobilization order: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="order-construct",
    description="Submit a construction order to build a new building"
)
@app_commands.describe(
    building_type="The building type ID to construct (e.g., 'barracks', 'forge')",
    territory_id="The territory ID where the building will be constructed",
    faction_id="Optional: Faction ID to use faction resources (requires CONSTRUCTION permission)"
)
async def order_construct_cmd(
    interaction: discord.Interaction,
    building_type: str,
    territory_id: str,
    faction_id: str = None
):
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

        success, message = await handlers.submit_construction_order(
            conn, building_type, territory_id, interaction.guild_id, character.id,
            faction_id=faction_id
        )

        if success:
            logger.info(f"User {interaction.user.name} submitted construction order for {building_type} in territory {territory_id}")
        else:
            logger.warning(f"User {interaction.user.name} failed to submit construction order: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="view-wars",
    description="View all ongoing wars"
)
async def view_wars_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message, wars = await handlers.view_wars(conn, interaction.guild_id)

        if not success or not wars:
            await interaction.followup.send(
                emotive_message(message),
                ephemeral=True
            )
            return

        # Build embed
        embed = discord.Embed(
            title="Ongoing Wars",
            color=discord.Color.dark_red()
        )

        for war in wars:
            side_a_names = [f['name'] for f in war['side_a']]
            side_b_names = [f['name'] for f in war['side_b']]

            field_name = f"War: {war['war_id']}"
            field_value = f"**Objective:** {war['objective']}\n"
            field_value += f"**Side A:** {', '.join(side_a_names) if side_a_names else 'None'}\n"
            field_value += f"**Side B:** {', '.join(side_b_names) if side_b_names else 'None'}\n"
            field_value += f"**Declared Turn:** {war['declared_turn']}"

            embed.add_field(name=field_name, value=field_value, inline=False)

        embed.set_footer(text=f"Total: {len(wars)} war(s)")
        await interaction.followup.send(embed=embed)


@tree.command(
    name="edit-war",
    description="[Admin] Edit a war's objective"
)
@app_commands.describe(
    war_id="War ID to edit",
    objective="New objective text"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def edit_war_cmd(interaction: discord.Interaction, war_id: str, objective: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.edit_war(conn, war_id, objective, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} edited war '{war_id}' objective to '{objective}'")
        else:
            logger.warning(f"Admin {interaction.user.name} failed to edit war: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="add-war-participant",
    description="[Admin] Add a faction to a war"
)
@app_commands.describe(
    war_id="War ID",
    faction_id="Faction ID to add",
    side="SIDE_A or SIDE_B"
)
@app_commands.choices(side=[
    app_commands.Choice(name="Side A", value="SIDE_A"),
    app_commands.Choice(name="Side B", value="SIDE_B"),
])
@app_commands.checks.has_permissions(manage_guild=True)
async def add_war_participant_cmd(interaction: discord.Interaction, war_id: str, faction_id: str, side: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.add_war_participant(
            conn, war_id, faction_id, side, interaction.guild_id
        )

        if success:
            logger.info(f"Admin {interaction.user.name} added faction '{faction_id}' to war '{war_id}' on {side}")
        else:
            logger.warning(f"Admin {interaction.user.name} failed to add war participant: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="remove-war-participant",
    description="[Admin] Remove a faction from a war"
)
@app_commands.describe(
    war_id="War ID",
    faction_id="Faction ID to remove"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def remove_war_participant_cmd(interaction: discord.Interaction, war_id: str, faction_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.remove_war_participant(
            conn, war_id, faction_id, interaction.guild_id
        )

        if success:
            logger.info(f"Admin {interaction.user.name} removed faction '{faction_id}' from war '{war_id}'")
        else:
            logger.warning(f"Admin {interaction.user.name} failed to remove war participant: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


@tree.command(
    name="delete-war",
    description="[Admin] Delete a war entirely"
)
@app_commands.describe(
    war_id="War ID to delete"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def delete_war_cmd(interaction: discord.Interaction, war_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        success, message = await handlers.delete_war(conn, war_id, interaction.guild_id)

        if success:
            logger.info(f"Admin {interaction.user.name} deleted war '{war_id}'")
        else:
            logger.warning(f"Admin {interaction.user.name} failed to delete war: {message}")

        await interaction.followup.send(
            emotive_message(message),
            ephemeral=not success
        )


client.run(BOT_TOKEN)
