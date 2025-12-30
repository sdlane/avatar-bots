import discord
from discord import app_commands
from discord.ext import commands, tasks
from helpers import *
from embeds import *
from views import *
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
async def view_territory(interaction: discord.Interaction, territory_id: int):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Fetch territory
        territory = await Territory.fetch_by_territory_id(conn, territory_id, interaction.guild_id)

        if not territory:
            await interaction.followup.send(
                emotive_message(f"Territory {territory_id} not found."),
                ephemeral=True
            )
            return

        # Fetch adjacent territories
        adjacent_ids = await TerritoryAdjacency.fetch_adjacent(conn, territory_id, interaction.guild_id)

        # Fetch controller faction name if exists
        controller_name = None
        if territory.controller_faction_id:
            faction = await Faction.fetch_by_id(conn, territory.controller_faction_id)
            if faction:
                controller_name = faction.name

        # Create and send embed
        embed = create_territory_embed(territory, adjacent_ids, controller_name)
        await interaction.followup.send(embed=embed)


@tree.command(
    name="view-faction",
    description="View detailed information about a faction"
)
@app_commands.describe(faction_id="The faction ID to view")
async def view_faction(interaction: discord.Interaction, faction_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Fetch faction
        faction = await Faction.fetch_by_faction_id(conn, faction_id, interaction.guild_id)

        if not faction:
            await interaction.followup.send(
                emotive_message(f"Faction '{faction_id}' not found."),
                ephemeral=True
            )
            return

        # Check if user is admin
        admin = is_admin(interaction)

        # Fetch leader (only for admins)
        leader = None
        if admin and faction.leader_character_id:
            leader = await Character.fetch_by_id(conn, faction.leader_character_id)

        # Fetch members (only for admins)
        members = []
        if admin:
            faction_members = await FactionMember.fetch_by_faction(conn, faction.id, interaction.guild_id)
            for fm in faction_members:
                char = await Character.fetch_by_id(conn, fm.character_id)
                if char:
                    members.append(char)

        # Create and send embed
        if admin:
            embed = create_faction_embed(faction, members, leader)
        else:
            # Limited info for non-admins
            embed = discord.Embed(
                title=f"⚔️ {faction.name}",
                description=f"Faction ID: `{faction.faction_id}`",
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
async def view_unit(interaction: discord.Interaction, unit_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Fetch unit
        unit = await Unit.fetch_by_unit_id(conn, unit_id, interaction.guild_id)

        if not unit:
            await interaction.followup.send(
                emotive_message(f"Unit '{unit_id}' not found."),
                ephemeral=True
            )
            return

        # Check if user is admin
        admin = is_admin(interaction)

        # Fetch related data
        unit_type = await UnitType.fetch_by_type_id(conn, unit.unit_type, None, interaction.guild_id)
        owner = await Character.fetch_by_id(conn, unit.owner_character_id) if unit.owner_character_id and admin else None
        commander = await Character.fetch_by_id(conn, unit.commander_character_id) if unit.commander_character_id and admin else None
        faction = await Faction.fetch_by_id(conn, unit.faction_id) if unit.faction_id else None

        # Create and send embed
        embed = create_unit_embed(unit, unit_type, owner, commander, faction, show_full_details=admin)
        await interaction.followup.send(embed=embed)


@tree.command(
    name="view-unit-type",
    description="View detailed information about a unit type"
)
@app_commands.describe(
    type_id="The unit type ID to view",
    nation="Optional: The nation (leave empty for nation-agnostic types)"
)
async def view_unit_type(interaction: discord.Interaction, type_id: str, nation: str = None):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Fetch unit type
        unit_type = await UnitType.fetch_by_type_id(conn, type_id, nation, interaction.guild_id)

        if not unit_type:
            if nation:
                await interaction.followup.send(
                    emotive_message(f"Unit type '{type_id}' for nation '{nation}' not found."),
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    emotive_message(f"Unit type '{type_id}' not found."),
                    ephemeral=True
                )
            return

        # Create and send embed
        embed = create_unit_type_embed(unit_type)
        await interaction.followup.send(embed=embed)


@tree.command(
    name="my-resources",
    description="View your character's resource inventory"
)
async def my_resources(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        # Find character for this user
        character = await Character.fetch_by_user_id(conn, interaction.user.id, interaction.guild_id)

        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character assigned. Ask a GM to assign you one using hawky."),
                ephemeral=True
            )
            return

        # Fetch resources
        resources = await PlayerResources.fetch_by_character(conn, character.id, interaction.guild_id)

        if not resources:
            # Create empty resources entry
            resources = PlayerResources(
                character_id=character.id,
                ore=0,
                lumber=0,
                coal=0,
                rations=0,
                cloth=0,
                guild_id=interaction.guild_id
            )

        # Create and send embed
        embed = create_resources_embed(character, resources)
        await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(
    name="my-faction",
    description="View your character's faction membership"
)
async def my_faction(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        # Find character for this user
        character = await Character.fetch_by_user_id(conn, interaction.user.id, interaction.guild_id)

        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character assigned. Ask a GM to assign you one using hawky."),
                ephemeral=True
            )
            return

        # Find faction membership
        faction_member = await FactionMember.fetch_by_character(conn, character.id, interaction.guild_id)

        if not faction_member:
            await interaction.followup.send(
                emotive_message(f"{character.name} is not a member of any faction."),
                ephemeral=True
            )
            return

        # Fetch faction details
        faction = await Faction.fetch_by_id(conn, faction_member.faction_id)

        if not faction:
            await interaction.followup.send(
                emotive_message("Faction data not found."),
                ephemeral=True
            )
            return

        # Fetch leader and all members
        leader = None
        if faction.leader_character_id:
            leader = await Character.fetch_by_id(conn, faction.leader_character_id)

        faction_members = await FactionMember.fetch_by_faction(conn, faction.id, interaction.guild_id)
        members = []
        for fm in faction_members:
            char = await Character.fetch_by_id(conn, fm.character_id)
            if char:
                members.append(char)

        # Create and send embed
        embed = create_faction_embed(faction, members, leader)
        embed.description = f"Your character's faction\nFaction ID: `{faction.faction_id}`"
        await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(
    name="my-units",
    description="View units your character owns or commands"
)
async def my_units(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        # Find character for this user
        character = await Character.fetch_by_user_id(conn, interaction.user.id, interaction.guild_id)

        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character assigned. Ask a GM to assign you one using hawky."),
                ephemeral=True
            )
            return

        # Fetch owned and commanded units
        owned_units = await Unit.fetch_by_owner(conn, character.id, interaction.guild_id)
        commanded_units = await Unit.fetch_by_commander(conn, character.id, interaction.guild_id)

        # Combine and deduplicate
        all_units = {unit.id: unit for unit in owned_units + commanded_units}.values()

        if not all_units:
            await interaction.followup.send(
                emotive_message(f"{character.name} doesn't own or command any units."),
                ephemeral=True
            )
            return

        # Create summary embed
        embed = discord.Embed(
            title=f"🎖️ {character.name}'s Units",
            color=discord.Color.blue()
        )

        owned_list = []
        commanded_list = []

        for unit in all_units:
            unit_str = f"`{unit.unit_id}`: {unit.name or unit.unit_type}"
            if unit.current_territory_id is not None:
                unit_str += f" (Territory {unit.current_territory_id})"

            if unit.owner_character_id == character.id:
                owned_list.append(unit_str)
            if unit.commander_character_id == character.id:
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
    description="View territories controlled by your faction"
)
async def my_territories(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        # Find character for this user
        character = await Character.fetch_by_user_id(conn, interaction.user.id, interaction.guild_id)

        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character assigned. Ask a GM to assign you one using hawky."),
                ephemeral=True
            )
            return

        # Find faction membership
        faction_member = await FactionMember.fetch_by_character(conn, character.id, interaction.guild_id)

        if not faction_member:
            await interaction.followup.send(
                emotive_message(f"{character.name} is not a member of any faction."),
                ephemeral=True
            )
            return

        # Fetch faction
        faction = await Faction.fetch_by_id(conn, faction_member.faction_id)

        if not faction:
            await interaction.followup.send(
                emotive_message("Faction data not found."),
                ephemeral=True
            )
            return

        # Fetch territories controlled by this faction
        territories = await Territory.fetch_by_controller(conn, faction.id, interaction.guild_id)

        if not territories:
            await interaction.followup.send(
                emotive_message(f"The {faction.name} doesn't control any territories."),
                ephemeral=True
            )
            return

        # Create summary embed
        embed = discord.Embed(
            title=f"🗺️ {faction.name} Territories",
            description=f"{len(territories)} territories controlled",
            color=discord.Color.green()
        )

        territory_list = []
        for territory in territories:
            # Get adjacent territories
            adjacent_ids = await TerritoryAdjacency.fetch_adjacent(conn, territory.territory_id, interaction.guild_id)

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
async def my_units_list(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        # Find character for this user
        character = await Character.fetch_by_user_id(conn, interaction.user.id, interaction.guild_id)

        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character assigned. Ask a GM to assign you one using hawky."),
                ephemeral=True
            )
            return

        # Fetch owned and commanded units
        owned_units = await Unit.fetch_by_owner(conn, character.id, interaction.guild_id)
        commanded_units = await Unit.fetch_by_commander(conn, character.id, interaction.guild_id)

        # Combine and deduplicate
        all_units = {unit.id: unit for unit in owned_units + commanded_units}.values()

        if not all_units:
            await interaction.followup.send(
                emotive_message(f"{character.name} doesn't own or command any units."),
                ephemeral=True
            )
            return

        # Create list of unit IDs
        unit_ids = [unit.unit_id for unit in all_units]

        await interaction.followup.send(
            f"**Your unit IDs:**\n`{', '.join(unit_ids)}`\n\nUse `/view-unit <unit_id>` for details.",
            ephemeral=True
        )


@tree.command(
    name="my-territories-list",
    description="List IDs of territories controlled by your faction"
)
async def my_territories_list(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async with db_pool.acquire() as conn:
        # Find character for this user
        character = await Character.fetch_by_user_id(conn, interaction.user.id, interaction.guild_id)

        if not character:
            await interaction.followup.send(
                emotive_message("You don't have a character assigned. Ask a GM to assign you one using hawky."),
                ephemeral=True
            )
            return

        # Find faction membership
        faction_member = await FactionMember.fetch_by_character(conn, character.id, interaction.guild_id)

        if not faction_member:
            await interaction.followup.send(
                emotive_message(f"{character.name} is not a member of any faction."),
                ephemeral=True
            )
            return

        # Fetch faction
        faction = await Faction.fetch_by_id(conn, faction_member.faction_id)

        if not faction:
            await interaction.followup.send(
                emotive_message("Faction data not found."),
                ephemeral=True
            )
            return

        # Fetch territories controlled by this faction
        territories = await Territory.fetch_by_controller(conn, faction.id, interaction.guild_id)

        if not territories:
            await interaction.followup.send(
                emotive_message(f"The {faction.name} doesn't control any territories."),
                ephemeral=True
            )
            return

        # Create list of territory IDs
        territory_ids = [str(t.territory_id) for t in territories]

        await interaction.followup.send(
            f"**{faction.name} territory IDs:**\n`{', '.join(territory_ids)}`\n\nUse `/view-territory <territory_id>` for details.",
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
        await conn.execute("DELETE FROM ResourceTransfer WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM Faction WHERE guild_id = $1;", interaction.guild_id)
        await conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", interaction.guild_id)

        await interaction.followup.send(
            emotive_message("All wargame configuration has been cleared. The slate is clean.")
        )


@tree.command(
    name="list-factions",
    description="[Admin] List all faction IDs in this server"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def list_factions(interaction: discord.Interaction):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        factions = await Faction.fetch_all(conn, interaction.guild_id)

        if not factions:
            await interaction.followup.send(
                emotive_message("No factions found. Use `/create-test-config` to set up a test configuration.")
            )
            return

        faction_list = []
        for faction in factions:
            # Get member count
            members = await FactionMember.fetch_by_faction(conn, faction.id, interaction.guild_id)
            faction_list.append(f"`{faction.faction_id}`: {faction.name} ({len(members)} members)")

        embed = discord.Embed(
            title="⚔️ All Factions",
            description="\n".join(faction_list),
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Total: {len(factions)} factions")

        await interaction.followup.send(embed=embed)


@tree.command(
    name="list-territories",
    description="[Admin] List all territory IDs in this server"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def list_territories(interaction: discord.Interaction):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        territories = await Territory.fetch_all(conn, interaction.guild_id)

        if not territories:
            await interaction.followup.send(
                emotive_message("No territories found. Use `/create-test-config` to set up a test configuration.")
            )
            return

        territory_list = []
        for territory in territories:
            # Get controller faction name
            controller_name = "Uncontrolled"
            if territory.controller_faction_id:
                faction = await Faction.fetch_by_id(conn, territory.controller_faction_id)
                if faction:
                    controller_name = faction.name

            territory_list.append(
                f"`{territory.territory_id}`: {territory.name or 'Unnamed'} ({territory.terrain_type}) - {controller_name}"
            )

        embed = discord.Embed(
            title="🗺️ All Territories",
            description="\n".join(territory_list),
            color=discord.Color.green()
        )
        embed.set_footer(text=f"Total: {len(territories)} territories")

        await interaction.followup.send(embed=embed)


@tree.command(
    name="list-unit-types",
    description="[Admin] List all unit type IDs in this server"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def list_unit_types(interaction: discord.Interaction):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        unit_types = await UnitType.fetch_all(conn, interaction.guild_id)

        if not unit_types:
            await interaction.followup.send(
                emotive_message("No unit types found. Use `/create-test-config` to set up a test configuration.")
            )
            return

        unit_type_list = []
        for unit_type in unit_types:
            nation_str = f" ({unit_type.nation})" if unit_type.nation else " (any nation)"
            unit_type_list.append(f"`{unit_type.type_id}`: {unit_type.name}{nation_str}")

        embed = discord.Embed(
            title="📋 All Unit Types",
            description="\n".join(unit_type_list),
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Total: {len(unit_types)} unit types")

        await interaction.followup.send(embed=embed)


@tree.command(
    name="list-units",
    description="[Admin] List all unit IDs in this server"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def list_units(interaction: discord.Interaction):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        units = await Unit.fetch_all(conn, interaction.guild_id)

        if not units:
            await interaction.followup.send(
                emotive_message("No units found.")
            )
            return

        unit_list = []
        for unit in units:
            # Get owner name
            owner = await Character.fetch_by_id(conn, unit.owner_character_id)
            owner_name = owner.name if owner else "Unknown"

            # Get faction name
            faction_name = "No faction"
            if unit.faction_id:
                faction = await Faction.fetch_by_id(conn, unit.faction_id)
                if faction:
                    faction_name = faction.name

            location = f"Territory {unit.current_territory_id}" if unit.current_territory_id is not None else "Undeployed"

            unit_list.append(
                f"`{unit.unit_id}`: {unit.name or unit.unit_type} - {faction_name} - {location} (Owner: {owner_name})"
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

        embed.set_footer(text=f"Total: {len(units)} units")

        await interaction.followup.send(embed=embed)


@tree.command(
    name="create-test-config",
    description="[Admin] Create a test wargame configuration in this server"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def create_test_config(interaction: discord.Interaction):
    await interaction.response.defer()

    from config_manager import ConfigManager

    # Import sample config from test file
    test_config = """
wargame:
  turn: 0
  max_movement_stat: 4

factions:
  - faction_id: "fire-nation"
    name: "Fire Nation"
    members: []

  - faction_id: "earth-kingdom"
    name: "Earth Kingdom"
    members: []

territories:
  - territory_id: 1
    name: "Fire Nation Capital"
    terrain_type: "plains"
    original_nation: "fire-nation"
    controller_faction_id: "fire-nation"
    production:
      ore: 5
      lumber: 3
      coal: 2
      rations: 8
      cloth: 4
    adjacent_to: [2]

  - territory_id: 2
    name: "Earth Kingdom Territory"
    terrain_type: "mountain"
    original_nation: "earth-kingdom"
    controller_faction_id: "earth-kingdom"
    production:
      ore: 10
      lumber: 1
      coal: 5
      rations: 2
      cloth: 0
    adjacent_to: [1]

unit_types:
  - type_id: "infantry"
    name: "Infantry Division"
    nation: "fire-nation"
    stats:
      movement: 2
      organization: 10
      attack: 5
      defense: 5
      siege_attack: 2
      siege_defense: 3
    cost:
      ore: 5
      lumber: 2
      rations: 10
      cloth: 5
    upkeep:
      rations: 2
      cloth: 1

  - type_id: "cavalry"
    name: "Cavalry Division"
    nation: "earth-kingdom"
    stats:
      movement: 4
      organization: 8
      attack: 7
      defense: 3
      siege_attack: 1
      siege_defense: 2
    cost:
      ore: 3
      lumber: 5
      rations: 15
      cloth: 8
    upkeep:
      rations: 3
      cloth: 2
"""

    async with db_pool.acquire() as conn:
        success, message = await ConfigManager.import_config(conn, interaction.guild_id, test_config)

        if success:
            await interaction.followup.send(
                emotive_message(f"Test wargame configuration created successfully!\n\nCreated:\n• 2 factions\n• 2 territories\n• 2 unit types\n\nYou can now use `/view-territory`, `/view-faction`, and `/view-unit-type` commands.")
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
async def create_faction(interaction: discord.Interaction, faction_id: str, name: str, leader: str = None):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Check if faction already exists
        existing = await Faction.fetch_by_faction_id(conn, faction_id, interaction.guild_id)
        if existing:
            await interaction.followup.send(
                emotive_message(f"A faction with ID '{faction_id}' already exists."),
                ephemeral=True
            )
            return

        # Validate leader if provided
        leader_character_id = None
        if leader:
            leader_char = await Character.fetch_by_identifier(conn, leader, interaction.guild_id)
            if not leader_char:
                await interaction.followup.send(
                    emotive_message(f"Character '{leader}' not found. Create the character first using hawky."),
                    ephemeral=True
                )
                return
            leader_character_id = leader_char.id

        # Create faction
        faction = Faction(
            faction_id=faction_id,
            name=name,
            leader_character_id=leader_character_id,
            guild_id=interaction.guild_id
        )

        await faction.upsert(conn)

        # Add leader as member if specified
        if leader_character_id:
            # Fetch the newly created faction to get its internal ID
            faction = await Faction.fetch_by_faction_id(conn, faction_id, interaction.guild_id)

            faction_member = FactionMember(
                faction_id=faction.id,
                character_id=leader_character_id,
                joined_turn=0,
                guild_id=interaction.guild_id
            )
            await faction_member.upsert(conn)

        if leader:
            await interaction.followup.send(
                emotive_message(f"Faction '{name}' created successfully with leader {leader}.")
            )
        else:
            await interaction.followup.send(
                emotive_message(f"Faction '{name}' created successfully.")
            )


@tree.command(
    name="delete-faction",
    description="[Admin] Delete a faction"
)
@app_commands.describe(faction_id="The faction ID to delete")
@app_commands.checks.has_permissions(manage_guild=True)
async def delete_faction(interaction: discord.Interaction, faction_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Check if faction exists
        faction = await Faction.fetch_by_faction_id(conn, faction_id, interaction.guild_id)
        if not faction:
            await interaction.followup.send(
                emotive_message(f"Faction '{faction_id}' not found."),
                ephemeral=True
            )
            return

        # Check if faction has units
        units = await Unit.fetch_by_faction(conn, faction.id, interaction.guild_id)
        if units:
            await interaction.followup.send(
                emotive_message(f"Cannot delete faction '{faction_id}' - it has {len(units)} units. Delete or reassign the units first."),
                ephemeral=True
            )
            return

        # Delete faction (CASCADE will delete FactionMember entries)
        await faction.delete(conn)

        await interaction.followup.send(
            emotive_message(f"Faction '{faction.name}' has been deleted.")
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
async def set_faction_leader(interaction: discord.Interaction, faction_id: str, leader: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Check if faction exists
        faction = await Faction.fetch_by_faction_id(conn, faction_id, interaction.guild_id)
        if not faction:
            await interaction.followup.send(
                emotive_message(f"Faction '{faction_id}' not found."),
                ephemeral=True
            )
            return

        # Handle removing leader
        if leader.lower() == 'none':
            faction.leader_character_id = None
            await faction.upsert(conn)
            await interaction.followup.send(
                emotive_message(f"Removed leader from faction '{faction.name}'.")
            )
            return

        # Validate new leader
        leader_char = await Character.fetch_by_identifier(conn, leader, interaction.guild_id)
        if not leader_char:
            await interaction.followup.send(
                emotive_message(f"Character '{leader}' not found."),
                ephemeral=True
            )
            return

        # Check if leader is a member of the faction
        faction_member = await FactionMember.fetch_by_character(conn, leader_char.id, interaction.guild_id)
        if not faction_member or faction_member.faction_id != faction.id:
            await interaction.followup.send(
                emotive_message(f"{leader_char.name} is not a member of {faction.name}. Add them as a member first."),
                ephemeral=True
            )
            return

        # Update leader
        faction.leader_character_id = leader_char.id
        await faction.upsert(conn)

        await interaction.followup.send(
            emotive_message(f"{leader_char.name} is now the leader of {faction.name}.")
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
async def add_faction_member(interaction: discord.Interaction, faction_id: str, character: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Check if faction exists
        faction = await Faction.fetch_by_faction_id(conn, faction_id, interaction.guild_id)
        if not faction:
            await interaction.followup.send(
                emotive_message(f"Faction '{faction_id}' not found."),
                ephemeral=True
            )
            return

        # Validate character
        char = await Character.fetch_by_identifier(conn, character, interaction.guild_id)
        if not char:
            await interaction.followup.send(
                emotive_message(f"Character '{character}' not found."),
                ephemeral=True
            )
            return

        # Check if already in a faction
        existing_membership = await FactionMember.fetch_by_character(conn, char.id, interaction.guild_id)
        if existing_membership:
            existing_faction = await Faction.fetch_by_id(conn, existing_membership.faction_id)
            await interaction.followup.send(
                emotive_message(f"{char.name} is already a member of {existing_faction.name}. Remove them first."),
                ephemeral=True
            )
            return

        # Get current turn
        wargame_config = await conn.fetchrow(
            "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
            interaction.guild_id
        )
        current_turn = wargame_config['current_turn'] if wargame_config else 0

        # Add member
        faction_member = FactionMember(
            faction_id=faction.id,
            character_id=char.id,
            joined_turn=current_turn,
            guild_id=interaction.guild_id
        )
        await faction_member.upsert(conn)

        await interaction.followup.send(
            emotive_message(f"{char.name} has joined {faction.name}.")
        )


@tree.command(
    name="remove-faction-member",
    description="[Admin] Remove a member from their faction"
)
@app_commands.describe(character="Character identifier to remove")
@app_commands.checks.has_permissions(manage_guild=True)
async def remove_faction_member(interaction: discord.Interaction, character: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Validate character
        char = await Character.fetch_by_identifier(conn, character, interaction.guild_id)
        if not char:
            await interaction.followup.send(
                emotive_message(f"Character '{character}' not found."),
                ephemeral=True
            )
            return

        # Check if in a faction
        faction_member = await FactionMember.fetch_by_character(conn, char.id, interaction.guild_id)
        if not faction_member:
            await interaction.followup.send(
                emotive_message(f"{char.name} is not a member of any faction."),
                ephemeral=True
            )
            return

        # Get faction name
        faction = await Faction.fetch_by_id(conn, faction_member.faction_id)

        # Check if character is the leader
        if faction.leader_character_id == char.id:
            await interaction.followup.send(
                emotive_message(f"{char.name} is the leader of {faction.name}. Assign a new leader first using `/set-faction-leader`."),
                ephemeral=True
            )
            return

        # Remove member
        await faction_member.delete(conn)

        await interaction.followup.send(
            emotive_message(f"{char.name} has left {faction.name}.")
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
async def create_territory(interaction: discord.Interaction, territory_id: int, terrain_type: str, name: str = None):
    await interaction.response.defer()

    # Validate terrain type
    valid_terrains = ["plains", "mountain", "desert", "ocean", "lake"]
    if terrain_type.lower() not in valid_terrains:
        await interaction.followup.send(
            emotive_message(f"Invalid terrain type. Must be one of: {', '.join(valid_terrains)}"),
            ephemeral=True
        )
        return

    async with db_pool.acquire() as conn:
        # Check if territory already exists
        existing = await Territory.fetch_by_territory_id(conn, territory_id, interaction.guild_id)
        if existing:
            await interaction.followup.send(
                emotive_message(f"Territory {territory_id} already exists."),
                ephemeral=True
            )
            return

        # Create territory
        territory = Territory(
            territory_id=territory_id,
            name=name,
            terrain_type=terrain_type.lower(),
            ore_production=0,
            lumber_production=0,
            coal_production=0,
            rations_production=0,
            cloth_production=0,
            controller_faction_id=None,
            original_nation=None,
            guild_id=interaction.guild_id
        )

        await territory.upsert(conn)

        if name:
            await interaction.followup.send(
                emotive_message(f"Territory {territory_id} '{name}' created successfully.")
            )
        else:
            await interaction.followup.send(
                emotive_message(f"Territory {territory_id} created successfully.")
            )


@tree.command(
    name="edit-territory",
    description="[Admin] Edit territory properties"
)
@app_commands.describe(territory_id="The territory ID to edit")
@app_commands.checks.has_permissions(manage_guild=True)
async def edit_territory(interaction: discord.Interaction, territory_id: int):
    async with db_pool.acquire() as conn:
        # Fetch territory
        territory = await Territory.fetch_by_territory_id(conn, territory_id, interaction.guild_id)

        if not territory:
            await interaction.response.send_message(
                emotive_message(f"Territory {territory_id} not found."),
                ephemeral=True
            )
            return

        # Show modal
        modal = EditTerritoryModal(territory)
        await interaction.response.send_modal(modal)


@tree.command(
    name="delete-territory",
    description="[Admin] Delete a territory"
)
@app_commands.describe(territory_id="The territory ID to delete")
@app_commands.checks.has_permissions(manage_guild=True)
async def delete_territory(interaction: discord.Interaction, territory_id: int):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Check if territory exists
        territory = await Territory.fetch_by_territory_id(conn, territory_id, interaction.guild_id)
        if not territory:
            await interaction.followup.send(
                emotive_message(f"Territory {territory_id} not found."),
                ephemeral=True
            )
            return

        # Check if territory has units
        units = await conn.fetch(
            "SELECT * FROM Unit WHERE current_territory_id = $1 AND guild_id = $2;",
            territory_id,
            interaction.guild_id
        )
        if units:
            await interaction.followup.send(
                emotive_message(f"Cannot delete territory {territory_id} - it contains {len(units)} units. Remove or move them first."),
                ephemeral=True
            )
            return

        # Delete territory (CASCADE will delete adjacencies)
        await territory.delete(conn)

        await interaction.followup.send(
            emotive_message(f"Territory {territory_id} has been deleted.")
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
async def set_territory_controller(interaction: discord.Interaction, territory_id: int, faction_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Check if territory exists
        territory = await Territory.fetch_by_territory_id(conn, territory_id, interaction.guild_id)
        if not territory:
            await interaction.followup.send(
                emotive_message(f"Territory {territory_id} not found."),
                ephemeral=True
            )
            return

        # Handle removing controller
        if faction_id.lower() == 'none':
            territory.controller_faction_id = None
            await territory.upsert(conn)
            await interaction.followup.send(
                emotive_message(f"Territory {territory_id} is now uncontrolled.")
            )
            return

        # Validate faction
        faction = await Faction.fetch_by_faction_id(conn, faction_id, interaction.guild_id)
        if not faction:
            await interaction.followup.send(
                emotive_message(f"Faction '{faction_id}' not found."),
                ephemeral=True
            )
            return

        # Update controller
        territory.controller_faction_id = faction.id
        await territory.upsert(conn)

        await interaction.followup.send(
            emotive_message(f"Territory {territory_id} is now controlled by {faction.name}.")
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
async def add_adjacency(interaction: discord.Interaction, territory_id_1: int, territory_id_2: int):
    await interaction.response.defer()

    if territory_id_1 == territory_id_2:
        await interaction.followup.send(
            emotive_message("A territory cannot be adjacent to itself."),
            ephemeral=True
        )
        return

    async with db_pool.acquire() as conn:
        # Check if both territories exist
        territory1 = await Territory.fetch_by_territory_id(conn, territory_id_1, interaction.guild_id)
        territory2 = await Territory.fetch_by_territory_id(conn, territory_id_2, interaction.guild_id)

        if not territory1:
            await interaction.followup.send(
                emotive_message(f"Territory {territory_id_1} not found."),
                ephemeral=True
            )
            return

        if not territory2:
            await interaction.followup.send(
                emotive_message(f"Territory {territory_id_2} not found."),
                ephemeral=True
            )
            return

        # Check if adjacency already exists
        adjacency = TerritoryAdjacency(
            territory_a_id=min(territory_id_1, territory_id_2),
            territory_b_id=max(territory_id_1, territory_id_2),
            guild_id=interaction.guild_id
        )

        try:
            await adjacency.upsert(conn)
            await interaction.followup.send(
                emotive_message(f"Territories {territory_id_1} and {territory_id_2} are now adjacent.")
            )
        except Exception as e:
            if "duplicate key" in str(e).lower():
                await interaction.followup.send(
                    emotive_message(f"Territories {territory_id_1} and {territory_id_2} are already adjacent."),
                    ephemeral=True
                )
            else:
                raise


@tree.command(
    name="remove-adjacency",
    description="[Admin] Remove adjacency between two territories"
)
@app_commands.describe(
    territory_id_1="First territory ID",
    territory_id_2="Second territory ID"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def remove_adjacency(interaction: discord.Interaction, territory_id_1: int, territory_id_2: int):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Delete the adjacency (order doesn't matter due to CHECK constraint)
        result = await conn.execute(
            """
            DELETE FROM TerritoryAdjacency
            WHERE guild_id = $1
            AND ((territory_a_id = $2 AND territory_b_id = $3)
                 OR (territory_a_id = $3 AND territory_b_id = $2));
            """,
            interaction.guild_id,
            min(territory_id_1, territory_id_2),
            max(territory_id_1, territory_id_2)
        )

        if result == "DELETE 0":
            await interaction.followup.send(
                emotive_message(f"Territories {territory_id_1} and {territory_id_2} are not adjacent."),
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                emotive_message(f"Removed adjacency between territories {territory_id_1} and {territory_id_2}.")
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
async def create_unit_type(interaction: discord.Interaction, type_id: str, name: str, nation: str = None):
    async with db_pool.acquire() as conn:
        # Check if unit type already exists
        existing = await UnitType.fetch_by_type_id(conn, type_id, nation, interaction.guild_id)
        if existing:
            if nation:
                await interaction.response.send_message(
                    emotive_message(f"Unit type '{type_id}' for nation '{nation}' already exists."),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    emotive_message(f"Unit type '{type_id}' already exists."),
                    ephemeral=True
                )
            return

        # Show modal for stats/costs
        modal = EditUnitTypeModal(unit_type=None, type_id=type_id, name=name, nation=nation)
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
async def edit_unit_type(interaction: discord.Interaction, type_id: str, nation: str = None):
    async with db_pool.acquire() as conn:
        # Fetch unit type
        unit_type = await UnitType.fetch_by_type_id(conn, type_id, nation, interaction.guild_id)

        if not unit_type:
            if nation:
                await interaction.response.send_message(
                    emotive_message(f"Unit type '{type_id}' for nation '{nation}' not found."),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    emotive_message(f"Unit type '{type_id}' not found."),
                    ephemeral=True
                )
            return

        # Show modal
        modal = EditUnitTypeModal(unit_type=unit_type)
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
async def delete_unit_type(interaction: discord.Interaction, type_id: str, nation: str = None):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Fetch unit type
        unit_type = await UnitType.fetch_by_type_id(conn, type_id, nation, interaction.guild_id)

        if not unit_type:
            if nation:
                await interaction.followup.send(
                    emotive_message(f"Unit type '{type_id}' for nation '{nation}' not found."),
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    emotive_message(f"Unit type '{type_id}' not found."),
                    ephemeral=True
                )
            return

        # Check if any units use this type
        units = await conn.fetch(
            "SELECT * FROM Unit WHERE unit_type = $1 AND guild_id = $2;",
            type_id,
            interaction.guild_id
        )

        if units:
            await interaction.followup.send(
                emotive_message(f"Cannot delete unit type '{type_id}' - {len(units)} units are using it. Delete those units first."),
                ephemeral=True
            )
            return

        # Delete unit type
        await unit_type.delete(conn)

        await interaction.followup.send(
            emotive_message(f"Unit type '{unit_type.name}' has been deleted.")
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
async def create_unit(interaction: discord.Interaction, unit_id: str, unit_type: str, owner: str, territory_id: int):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Check if unit already exists
        existing = await Unit.fetch_by_unit_id(conn, unit_id, interaction.guild_id)
        if existing:
            await interaction.followup.send(
                emotive_message(f"Unit '{unit_id}' already exists."),
                ephemeral=True
            )
            return

        # Validate owner character
        owner_char = await Character.fetch_by_identifier(conn, owner, interaction.guild_id)
        if not owner_char:
            await interaction.followup.send(
                emotive_message(f"Character '{owner}' not found."),
                ephemeral=True
            )
            return

        # Get owner's faction
        faction_member = await FactionMember.fetch_by_character(conn, owner_char.id, interaction.guild_id)
        faction_id = faction_member.faction_id if faction_member else None

        # Determine nation from faction
        faction_nation = None
        if faction_id:
            faction_obj = await Faction.fetch_by_id(conn, faction_id)
            if faction_obj:
                # Get nation from faction's controlled territories
                territory_with_nation = await conn.fetchrow(
                    "SELECT original_nation FROM Territory WHERE controller_faction_id = $1 AND guild_id = $2 AND original_nation IS NOT NULL LIMIT 1;",
                    faction_id, interaction.guild_id
                )
                if territory_with_nation:
                    faction_nation = territory_with_nation['original_nation']

        # Fetch unit type (try with nation first, then nation-agnostic)
        unit_type_obj = await UnitType.fetch_by_type_id(conn, unit_type, faction_nation, interaction.guild_id)
        if not unit_type_obj and faction_nation:
            # Try nation-agnostic as fallback
            unit_type_obj = await UnitType.fetch_by_type_id(conn, unit_type, None, interaction.guild_id)

        if not unit_type_obj:
            await interaction.followup.send(
                emotive_message(f"Unit type '{unit_type}' not found."),
                ephemeral=True
            )
            return

        # Validate territory
        territory = await Territory.fetch_by_territory_id(conn, territory_id, interaction.guild_id)
        if not territory:
            await interaction.followup.send(
                emotive_message(f"Territory {territory_id} not found."),
                ephemeral=True
            )
            return

        # Create unit from unit type
        unit = Unit(
            unit_id=unit_id,
            name=None,
            unit_type=unit_type,
            owner_character_id=owner_char.id,
            commander_character_id=None,
            commander_assigned_turn=None,
            faction_id=faction_id,
            movement=unit_type_obj.movement,
            organization=unit_type_obj.organization,
            max_organization=unit_type_obj.organization,
            attack=unit_type_obj.attack,
            defense=unit_type_obj.defense,
            siege_attack=unit_type_obj.siege_attack,
            siege_defense=unit_type_obj.siege_defense,
            size=unit_type_obj.size,
            capacity=unit_type_obj.capacity,
            current_territory_id=territory_id,
            is_naval=unit_type_obj.is_naval,
            upkeep_ore=unit_type_obj.upkeep_ore,
            upkeep_lumber=unit_type_obj.upkeep_lumber,
            upkeep_coal=unit_type_obj.upkeep_coal,
            upkeep_rations=unit_type_obj.upkeep_rations,
            upkeep_cloth=unit_type_obj.upkeep_cloth,
            keywords=unit_type_obj.keywords.copy() if unit_type_obj.keywords else [],
            guild_id=interaction.guild_id
        )

        await unit.upsert(conn)

        await interaction.followup.send(
            emotive_message(f"Unit '{unit_id}' created successfully in territory {territory_id}.")
        )


@tree.command(
    name="delete-unit",
    description="[Admin] Delete a unit"
)
@app_commands.describe(unit_id="The unit ID to delete")
@app_commands.checks.has_permissions(manage_guild=True)
async def delete_unit(interaction: discord.Interaction, unit_id: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Fetch unit
        unit = await Unit.fetch_by_unit_id(conn, unit_id, interaction.guild_id)

        if not unit:
            await interaction.followup.send(
                emotive_message(f"Unit '{unit_id}' not found."),
                ephemeral=True
            )
            return

        # Delete unit
        await unit.delete(conn)

        await interaction.followup.send(
            emotive_message(f"Unit '{unit_id}' has been deleted.")
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
async def set_unit_commander(interaction: discord.Interaction, unit_id: str, commander: str):
    await interaction.response.defer()

    async with db_pool.acquire() as conn:
        # Fetch unit
        unit = await Unit.fetch_by_unit_id(conn, unit_id, interaction.guild_id)

        if not unit:
            await interaction.followup.send(
                emotive_message(f"Unit '{unit_id}' not found."),
                ephemeral=True
            )
            return

        # Handle removing commander
        if commander.lower() == 'none':
            unit.commander_character_id = None
            unit.commander_assigned_turn = None
            await unit.upsert(conn)
            await interaction.followup.send(
                emotive_message(f"Removed commander from unit '{unit_id}'.")
            )
            return

        # Validate commander character
        commander_char = await Character.fetch_by_identifier(conn, commander, interaction.guild_id)
        if not commander_char:
            await interaction.followup.send(
                emotive_message(f"Character '{commander}' not found."),
                ephemeral=True
            )
            return

        # Check if commander is in the same faction as the unit
        if unit.faction_id:
            commander_faction = await FactionMember.fetch_by_character(conn, commander_char.id, interaction.guild_id)
            if not commander_faction or commander_faction.faction_id != unit.faction_id:
                faction = await Faction.fetch_by_id(conn, unit.faction_id)
                await interaction.followup.send(
                    emotive_message(f"{commander_char.name} is not a member of {faction.name}. Commanders must be in the same faction as their unit."),
                    ephemeral=True
                )
                return

        # Get current turn
        wargame_config = await conn.fetchrow(
            "SELECT current_turn FROM WargameConfig WHERE guild_id = $1;",
            interaction.guild_id
        )
        current_turn = wargame_config['current_turn'] if wargame_config else 0

        # Assign commander
        unit.commander_character_id = commander_char.id
        unit.commander_assigned_turn = current_turn
        await unit.upsert(conn)

        await interaction.followup.send(
            emotive_message(f"{commander_char.name} is now the commander of unit '{unit_id}'.")
        )


# Resource Management Commands
@tree.command(
    name="modify-resources",
    description="[Admin] Modify a player's resource inventory"
)
@app_commands.describe(character="Character identifier")
@app_commands.checks.has_permissions(manage_guild=True)
async def modify_resources(interaction: discord.Interaction, character: str):
    async with db_pool.acquire() as conn:
        # Validate character
        char = await Character.fetch_by_identifier(conn, character, interaction.guild_id)
        if not char:
            await interaction.response.send_message(
                emotive_message(f"Character '{character}' not found."),
                ephemeral=True
            )
            return

        # Fetch or create resources
        resources = await PlayerResources.fetch_by_character(conn, char.id, interaction.guild_id)
        if not resources:
            # Create empty resources entry
            resources = PlayerResources(
                character_id=char.id,
                ore=0,
                lumber=0,
                coal=0,
                rations=0,
                cloth=0,
                guild_id=interaction.guild_id
            )
            await resources.upsert(conn)

        # Show modal
        modal = ModifyResourcesModal(char, resources)
        await interaction.response.send_modal(modal)


client.run(BOT_TOKEN)
