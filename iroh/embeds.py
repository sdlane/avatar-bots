"""
Helper functions for creating rich Discord embeds for wargame data display.
"""
import discord
from typing import List, Optional, Tuple
from db import (
    Territory, Faction, Unit, UnitType, BuildingType, Building, PlayerResources,
    WargameConfig, Character, FactionMember
)


def create_territory_embed(territory: Territory, adjacent_ids: List[int], controller_name: Optional[str] = None,
                           buildings: Optional[List[Building]] = None) -> discord.Embed:
    """Create a rich embed displaying territory information."""
    embed = discord.Embed(
        title=f"🗺️ Territory {territory.territory_id}: {territory.name or 'Unnamed'}",
        color=discord.Color.green()
    )

    # Basic info
    embed.add_field(
        name="Terrain",
        value=territory.terrain_type.capitalize(),
        inline=True
    )

    if territory.original_nation:
        embed.add_field(
            name="Original Nation",
            value=territory.original_nation,
            inline=True
        )

    if controller_name:
        embed.add_field(
            name="Controller",
            value=controller_name,
            inline=True
        )
    elif territory.controller_character_id:
        embed.add_field(
            name="Controller",
            value=f"Character ID: {territory.controller_character_id}",
            inline=True
        )
    else:
        embed.add_field(
            name="Controller",
            value="Uncontrolled",
            inline=True
        )

    # Production
    production_lines = []
    if territory.ore_production > 0:
        production_lines.append(f"⛏️ Ore: {territory.ore_production}")
    if territory.lumber_production > 0:
        production_lines.append(f"🪵 Lumber: {territory.lumber_production}")
    if territory.coal_production > 0:
        production_lines.append(f"⚫ Coal: {territory.coal_production}")
    if territory.rations_production > 0:
        production_lines.append(f"🍖 Rations: {territory.rations_production}")
    if territory.cloth_production > 0:
        production_lines.append(f"🧵 Cloth: {territory.cloth_production}")
    if territory.platinum_production > 0:
        production_lines.append(f"🪙 Platinum: {territory.platinum_production}")

    if production_lines:
        embed.add_field(
            name="Production (per turn)",
            value="\n".join(production_lines),
            inline=False
        )
    else:
        embed.add_field(
            name="Production (per turn)",
            value="None",
            inline=False
        )

    # Buildings
    if buildings:
        building_lines = []
        for b in buildings:
            status_emoji = "🏛️" if b.status == "ACTIVE" else "💀"
            display_name = b.name or b.building_id
            building_lines.append(f"{status_emoji} {display_name} ({b.building_type}) - Durability: {b.durability}")
        embed.add_field(
            name="Buildings",
            value="\n".join(building_lines),
            inline=False
        )

    # Keywords
    if territory.keywords:
        embed.add_field(
            name="Keywords",
            value=", ".join(territory.keywords),
            inline=False
        )

    # Adjacent territories
    if adjacent_ids:
        embed.add_field(
            name="Adjacent Territories",
            value=", ".join(str(tid) for tid in sorted(adjacent_ids)),
            inline=False
        )

    return embed


def create_faction_embed(faction: Faction, members: List[Character], leader: Optional[Character] = None,
                         show_spending: bool = False, viewer_is_member: bool = True) -> discord.Embed:
    """
    Create a rich embed displaying faction information.

    Args:
        faction: The faction to display
        members: List of member characters (used only if viewer_is_member)
        leader: Optional leader character (shown only if viewer_is_member)
        show_spending: Whether to show per-turn spending configuration
        viewer_is_member: If True, show full details (leader, members).
                          If False, show only faction name and nation.
    """
    embed = discord.Embed(
        title=f"⚔️ {faction.name}",
        description=f"Faction ID: `{faction.faction_id}`",
        color=discord.Color.red()
    )

    # Nation (visible to all)
    if faction.nation:
        embed.add_field(
            name="Nation",
            value=faction.nation,
            inline=True
        )

    # For non-members, only show nation - no leader or member details
    if not viewer_is_member:
        return embed

    # Leader (members only)
    if leader:
        embed.add_field(
            name="Leader",
            value=f"{leader.name} (`{leader.identifier}`)",
            inline=True
        )
    else:
        embed.add_field(
            name="Leader",
            value="None",
            inline=True
        )

    # Member count
    embed.add_field(
        name="Members",
        value=str(len(members)),
        inline=True
    )

    # List members
    if members:
        member_list = [f"• {char.name} (`{char.identifier}`)" for char in members]
        # Split into chunks if too many members
        if len(member_list) <= 10:
            embed.add_field(
                name="Member List",
                value="\n".join(member_list),
                inline=False
            )
        else:
            # Show first 10 and count remaining
            embed.add_field(
                name="Member List (first 10)",
                value="\n".join(member_list[:10]) + f"\n... and {len(member_list) - 10} more",
                inline=False
            )

    # Spending (if authorized to view)
    if show_spending:
        spending_parts = []
        if faction.ore_spending > 0:
            spending_parts.append(f"Ore: {faction.ore_spending}")
        if faction.lumber_spending > 0:
            spending_parts.append(f"Lumber: {faction.lumber_spending}")
        if faction.coal_spending > 0:
            spending_parts.append(f"Coal: {faction.coal_spending}")
        if faction.rations_spending > 0:
            spending_parts.append(f"Rations: {faction.rations_spending}")
        if faction.cloth_spending > 0:
            spending_parts.append(f"Cloth: {faction.cloth_spending}")
        if faction.platinum_spending > 0:
            spending_parts.append(f"Platinum: {faction.platinum_spending}")

        if spending_parts:
            embed.add_field(
                name="Per-Turn Spending",
                value="\n".join(spending_parts),
                inline=False
            )
        else:
            embed.add_field(
                name="Per-Turn Spending",
                value="None configured",
                inline=False
            )

    return embed


def create_unit_embed(unit: Unit, unit_type: Optional[UnitType] = None, owner: Optional[Character] = None,
                      commander: Optional[Character] = None, faction: Optional[Faction] = None,
                      viewer_has_full_access: bool = True,
                      naval_positions: Optional[List[str]] = None) -> discord.Embed:
    """
    Create a rich embed displaying unit information.

    Args:
        unit: The unit to display
        unit_type: Optional unit type for additional info
        owner: Optional owner character (shown only if viewer_has_full_access)
        commander: Optional commander character (shown only if viewer_has_full_access)
        faction: Optional faction for display
        viewer_has_full_access: If True, show owner/commander, current org, and location.
                                If False, show only public info (stats, max org, upkeep, keywords).
    """
    embed = discord.Embed(
        title=f"🎖️ {unit.name or unit.unit_id}",
        description=f"Unit ID: `{unit.unit_id}` | Type: {unit.unit_type}",
        color=discord.Color.blue()
    )

    # Ownership info (only for authorized viewers)
    if viewer_has_full_access:
        if owner:
            embed.add_field(
                name="Owner",
                value=f"{owner.name} (`{owner.identifier}`)",
                inline=True
            )

        if commander:
            embed.add_field(
                name="Commander",
                value=f"{commander.name} (`{commander.identifier}`)",
                inline=True
            )
        else:
            embed.add_field(
                name="Commander",
                value="None",
                inline=True
            )

    # Faction visible to all
    if faction:
        embed.add_field(
            name="Faction",
            value=faction.name,
            inline=True
        )

    # Location (only for authorized viewers)
    if viewer_has_full_access:
        if unit.is_naval and naval_positions:
            territories = ", ".join(naval_positions)
            embed.add_field(
                name="Location",
                value=f"Territories {territories}",
                inline=True
            )
        elif unit.current_territory_id is not None:
            embed.add_field(
                name="Location",
                value=f"Territory {unit.current_territory_id}",
                inline=True
            )
        else:
            embed.add_field(
                name="Location",
                value="Not deployed",
                inline=True
            )

    # Type
    embed.add_field(
        name="Type",
        value=f"{'🚢 Naval' if unit.is_naval else '🏃 Land'} Unit",
        inline=True
    )

    # Status (visible to all)
    status_emoji = "🟢" if unit.status == "ACTIVE" else "🔴"
    embed.add_field(
        name="Status",
        value=f"{status_emoji} {unit.status}",
        inline=True
    )

    # Combat stats are visible to all, but current organization only to authorized viewers
    if viewer_has_full_access:
        stats_lines = [
            f"**Movement:** {unit.movement}",
            f"**Organization:** {unit.organization}/{unit.max_organization}",
            f"**Attack:** {unit.attack} | **Defense:** {unit.defense}",
            f"**Siege Attack:** {unit.siege_attack} | **Siege Defense:** {unit.siege_defense}",
            f"**Size:** {unit.size} dot{'s' if unit.size != 1 else ''}"
        ]
    else:
        # Public view - show max org only, not current
        stats_lines = [
            f"**Movement:** {unit.movement}",
            f"**Max Organization:** {unit.max_organization}",
            f"**Attack:** {unit.attack} | **Defense:** {unit.defense}",
            f"**Siege Attack:** {unit.siege_attack} | **Siege Defense:** {unit.siege_defense}",
            f"**Size:** {unit.size} dot{'s' if unit.size != 1 else ''}"
        ]

    if unit.capacity > 0:
        stats_lines.append(f"**Capacity:** {unit.capacity} dot{'s' if unit.capacity != 1 else ''}")

    embed.add_field(
        name="Combat Statistics",
        value="\n".join(stats_lines),
        inline=False
    )

    # Upkeep (visible to all)
    upkeep_lines = []
    if unit.upkeep_ore > 0:
        upkeep_lines.append(f"⛏️ {unit.upkeep_ore}")
    if unit.upkeep_lumber > 0:
        upkeep_lines.append(f"🪵 {unit.upkeep_lumber}")
    if unit.upkeep_coal > 0:
        upkeep_lines.append(f"⚫ {unit.upkeep_coal}")
    if unit.upkeep_rations > 0:
        upkeep_lines.append(f"🍖 {unit.upkeep_rations}")
    if unit.upkeep_cloth > 0:
        upkeep_lines.append(f"🧵 {unit.upkeep_cloth}")
    if unit.upkeep_platinum > 0:
        upkeep_lines.append(f"🪙 {unit.upkeep_platinum}")

    if upkeep_lines:
        embed.add_field(
            name="Upkeep (per turn)",
            value=" | ".join(upkeep_lines),
            inline=False
        )

    # Keywords (visible to all)
    if unit.keywords:
        embed.add_field(
            name="Keywords",
            value=", ".join(unit.keywords),
            inline=False
        )

    return embed


def create_unit_type_embed(unit_type: UnitType) -> discord.Embed:
    """Create a rich embed displaying unit type information."""
    embed = discord.Embed(
        title=f"📋 {unit_type.name}",
        description=f"Type ID: `{unit_type.type_id}`",
        color=discord.Color.purple()
    )

    # Nation
    if unit_type.nation:
        embed.add_field(
            name="Nation",
            value=unit_type.nation,
            inline=True
        )
    else:
        embed.add_field(
            name="Nation",
            value="Any (nation-agnostic)",
            inline=True
        )

    # Type
    embed.add_field(
        name="Type",
        value=f"{'🚢 Naval' if unit_type.is_naval else '🏃 Land'} Unit",
        inline=True
    )

    # Stats
    stats_lines = [
        f"**Movement:** {unit_type.movement}",
        f"**Organization:** {unit_type.organization}",
        f"**Attack:** {unit_type.attack} | **Defense:** {unit_type.defense}",
        f"**Siege Attack:** {unit_type.siege_attack} | **Siege Defense:** {unit_type.siege_defense}",
        f"**Size:** {unit_type.size} dot{'s' if unit_type.size != 1 else ''}"
    ]

    if unit_type.capacity > 0:
        stats_lines.append(f"**Capacity:** {unit_type.capacity} dot{'s' if unit_type.capacity != 1 else ''}")

    embed.add_field(
        name="Combat Statistics",
        value="\n".join(stats_lines),
        inline=False
    )

    # Construction cost
    cost_lines = []
    if unit_type.cost_ore > 0:
        cost_lines.append(f"⛏️ {unit_type.cost_ore}")
    if unit_type.cost_lumber > 0:
        cost_lines.append(f"🪵 {unit_type.cost_lumber}")
    if unit_type.cost_coal > 0:
        cost_lines.append(f"⚫ {unit_type.cost_coal}")
    if unit_type.cost_rations > 0:
        cost_lines.append(f"🍖 {unit_type.cost_rations}")
    if unit_type.cost_cloth > 0:
        cost_lines.append(f"🧵 {unit_type.cost_cloth}")
    if unit_type.cost_platinum > 0:
        cost_lines.append(f"🪙 {unit_type.cost_platinum}")

    if cost_lines:
        embed.add_field(
            name="Construction Cost",
            value=" | ".join(cost_lines),
            inline=False
        )
    else:
        embed.add_field(
            name="Construction Cost",
            value="Free",
            inline=False
        )

    # Upkeep
    upkeep_lines = []
    if unit_type.upkeep_ore > 0:
        upkeep_lines.append(f"⛏️ {unit_type.upkeep_ore}")
    if unit_type.upkeep_lumber > 0:
        upkeep_lines.append(f"🪵 {unit_type.upkeep_lumber}")
    if unit_type.upkeep_coal > 0:
        upkeep_lines.append(f"⚫ {unit_type.upkeep_coal}")
    if unit_type.upkeep_rations > 0:
        upkeep_lines.append(f"🍖 {unit_type.upkeep_rations}")
    if unit_type.upkeep_cloth > 0:
        upkeep_lines.append(f"🧵 {unit_type.upkeep_cloth}")
    if unit_type.upkeep_platinum > 0:
        upkeep_lines.append(f"🪙 {unit_type.upkeep_platinum}")

    if upkeep_lines:
        embed.add_field(
            name="Upkeep (per turn)",
            value=" | ".join(upkeep_lines),
            inline=False
        )
    else:
        embed.add_field(
            name="Upkeep (per turn)",
            value="None",
            inline=False
        )

    # Keywords
    if unit_type.keywords:
        embed.add_field(
            name="Keywords",
            value=", ".join(unit_type.keywords),
            inline=False
        )

    return embed


def create_building_type_embed(building_type: BuildingType) -> discord.Embed:
    """Create a rich embed displaying building type information."""
    embed = discord.Embed(
        title=f"🏛️ {building_type.name}",
        description=f"Type ID: `{building_type.type_id}`",
        color=discord.Color.dark_teal()
    )

    # Description
    if building_type.description:
        embed.add_field(
            name="Description",
            value=building_type.description,
            inline=False
        )

    # Construction cost
    cost_lines = []
    if building_type.cost_ore > 0:
        cost_lines.append(f"⛏️ {building_type.cost_ore}")
    if building_type.cost_lumber > 0:
        cost_lines.append(f"🪵 {building_type.cost_lumber}")
    if building_type.cost_coal > 0:
        cost_lines.append(f"⚫ {building_type.cost_coal}")
    if building_type.cost_rations > 0:
        cost_lines.append(f"🍖 {building_type.cost_rations}")
    if building_type.cost_cloth > 0:
        cost_lines.append(f"🧵 {building_type.cost_cloth}")
    if building_type.cost_platinum > 0:
        cost_lines.append(f"🪙 {building_type.cost_platinum}")

    embed.add_field(
        name="Construction Cost",
        value=" | ".join(cost_lines) if cost_lines else "Free",
        inline=False
    )

    # Upkeep
    upkeep_lines = []
    if building_type.upkeep_ore > 0:
        upkeep_lines.append(f"⛏️ {building_type.upkeep_ore}")
    if building_type.upkeep_lumber > 0:
        upkeep_lines.append(f"🪵 {building_type.upkeep_lumber}")
    if building_type.upkeep_coal > 0:
        upkeep_lines.append(f"⚫ {building_type.upkeep_coal}")
    if building_type.upkeep_rations > 0:
        upkeep_lines.append(f"🍖 {building_type.upkeep_rations}")
    if building_type.upkeep_cloth > 0:
        upkeep_lines.append(f"🧵 {building_type.upkeep_cloth}")
    if building_type.upkeep_platinum > 0:
        upkeep_lines.append(f"🪙 {building_type.upkeep_platinum}")

    embed.add_field(
        name="Upkeep (per turn)",
        value=" | ".join(upkeep_lines) if upkeep_lines else "None",
        inline=False
    )

    # Keywords
    if building_type.keywords:
        embed.add_field(
            name="Keywords",
            value=", ".join(building_type.keywords),
            inline=False
        )

    return embed


def create_building_embed(building: Building, building_type: Optional[BuildingType] = None,
                          territory: Optional[Territory] = None) -> discord.Embed:
    """Create a rich embed displaying building information."""
    embed = discord.Embed(
        title=f"🏛️ {building.name or building.building_id}",
        description=f"Building ID: `{building.building_id}` | Type: {building.building_type}",
        color=discord.Color.teal()
    )

    # Status
    status_emoji = "✅" if building.status == "ACTIVE" else "💀"
    embed.add_field(
        name="Status",
        value=f"{status_emoji} {building.status}",
        inline=True
    )

    # Durability
    embed.add_field(
        name="Durability",
        value=str(building.durability),
        inline=True
    )

    # Location
    if territory:
        embed.add_field(
            name="Location",
            value=f"{territory.name or territory.territory_id} (Territory {territory.territory_id})",
            inline=True
        )
    elif building.territory_id:
        embed.add_field(
            name="Location",
            value=f"Territory {building.territory_id}",
            inline=True
        )
    else:
        embed.add_field(
            name="Location",
            value="Not placed",
            inline=True
        )

    # Building type info
    if building_type:
        if building_type.description:
            embed.add_field(
                name="Description",
                value=building_type.description,
                inline=False
            )

    # Upkeep
    upkeep_lines = []
    if building.upkeep_ore > 0:
        upkeep_lines.append(f"⛏️ {building.upkeep_ore}")
    if building.upkeep_lumber > 0:
        upkeep_lines.append(f"🪵 {building.upkeep_lumber}")
    if building.upkeep_coal > 0:
        upkeep_lines.append(f"⚫ {building.upkeep_coal}")
    if building.upkeep_rations > 0:
        upkeep_lines.append(f"🍖 {building.upkeep_rations}")
    if building.upkeep_cloth > 0:
        upkeep_lines.append(f"🧵 {building.upkeep_cloth}")
    if building.upkeep_platinum > 0:
        upkeep_lines.append(f"🪙 {building.upkeep_platinum}")

    embed.add_field(
        name="Upkeep (per turn)",
        value=" | ".join(upkeep_lines) if upkeep_lines else "None",
        inline=False
    )

    # Keywords
    if building.keywords:
        embed.add_field(
            name="Keywords",
            value=", ".join(building.keywords),
            inline=False
        )

    return embed


def create_resources_embed(character: Character, resources: PlayerResources) -> discord.Embed:
    """Create a rich embed displaying character's resources."""
    embed = discord.Embed(
        title=f"💰 Resources: {character.name}",
        description=f"Character: `{character.identifier}`",
        color=discord.Color.gold()
    )

    # Resource inventory
    resource_lines = [
        f"⛏️ **Ore:** {resources.ore}",
        f"🪵 **Lumber:** {resources.lumber}",
        f"⚫ **Coal:** {resources.coal}",
        f"🍖 **Rations:** {resources.rations}",
        f"🧵 **Cloth:** {resources.cloth}",
        f"🪙 **Platinum:** {resources.platinum}"
    ]

    embed.add_field(
        name="Inventory",
        value="\n".join(resource_lines),
        inline=False
    )

    # Total
    total = resources.ore + resources.lumber + resources.coal + resources.rations + resources.cloth + resources.platinum
    embed.add_field(
        name="Total Resources",
        value=str(total),
        inline=True
    )

    return embed


def create_modify_resources_embed(character: Character, resources: PlayerResources) -> discord.Embed:
    """Create embed for modifying character resources via button interface."""
    embed = discord.Embed(
        title=f"Modify Resources: {character.name}",
        description=f"Character: `{character.identifier}`",
        color=discord.Color.blue()
    )

    # Resource values
    resource_lines = [
        f"⛏️ **Ore:** {resources.ore}",
        f"🪵 **Lumber:** {resources.lumber}",
        f"⚫ **Coal:** {resources.coal}",
        f"🍖 **Rations:** {resources.rations}",
        f"🧵 **Cloth:** {resources.cloth}",
        f"🪙 **Platinum:** {resources.platinum}"
    ]

    embed.add_field(
        name="Current Values",
        value="\n".join(resource_lines),
        inline=False
    )

    embed.set_footer(text="Click a resource button to modify its value")

    return embed


def create_modify_character_production_embed(character: Character) -> discord.Embed:
    """Create embed for modifying character production via button interface."""
    embed = discord.Embed(
        title=f"Modify Production: {character.name}",
        description=f"Character: `{character.identifier}`\nPer-turn production values",
        color=discord.Color.green()
    )

    # Production values
    production_lines = [
        f"⛏️ **Ore:** {character.ore_production}",
        f"🪵 **Lumber:** {character.lumber_production}",
        f"⚫ **Coal:** {character.coal_production}",
        f"🍖 **Rations:** {character.rations_production}",
        f"🧵 **Cloth:** {character.cloth_production}",
        f"🪙 **Platinum:** {character.platinum_production}"
    ]

    embed.add_field(
        name="Current Production",
        value="\n".join(production_lines),
        inline=False
    )

    embed.set_footer(text="Click a resource button to modify its production value")

    return embed


def create_victory_points_embed(data: dict) -> discord.Embed:
    """Create embed for victory points view."""
    character = data['character']

    embed = discord.Embed(
        title=f"Victory Points - {character.name}",
        color=discord.Color.gold()
    )

    # Character's direct VPs (if any)
    character_vps = data.get('character_vps', 0)
    if character_vps > 0:
        embed.add_field(
            name=f"Personal VP Award",
            value=f"{character_vps} VP",
            inline=False
        )

    # Territory VPs
    personal_vps = data['personal_vps']
    territory_vps = data.get('territory_vps', personal_vps - character_vps)
    if data['territories']:
        territory_list = "\n".join([
            f"  {t.name or f'Territory {t.territory_id}'}: {vp} VP"
            for t, vp in data['territories']
        ])
        embed.add_field(
            name=f"Your Territories ({territory_vps} VP)",
            value=territory_list,
            inline=False
        )
    elif territory_vps > 0:
        embed.add_field(
            name="Your Territories",
            value=f"{territory_vps} VP from territories",
            inline=False
        )

    # Total personal VPs
    embed.add_field(
        name="Total Personal VPs",
        value=f"{personal_vps} VP",
        inline=False
    )

    # Show if this character is assigning VPs to another faction
    assigning_vps_to = data.get('assigning_vps_to')
    if assigning_vps_to:
        embed.add_field(
            name="VP Assignment Active",
            value=f"Your {personal_vps} VP are being assigned to **{assigning_vps_to.name}**",
            inline=False
        )

    # Faction info
    if data['faction']:
        faction = data['faction']
        embed.add_field(
            name=f"Faction: {faction.name}",
            value=f"Total faction VPs: {data['faction_total_vps']}",
            inline=False
        )

        # Member breakdown
        if data['faction_members_vps']:
            member_list = "\n".join([
                f"  {char.name}: {vp} VP"
                for char, vp in data['faction_members_vps']
            ])
            embed.add_field(
                name="Faction Member VPs",
                value=member_list,
                inline=False
            )

        # Members assigning VPs elsewhere
        members_assigning_away = data.get('members_assigning_away', [])
        if members_assigning_away:
            away_list = "\n".join([
                f"  {char.name}: {vp} VP → {target_faction.name if target_faction else 'Unknown'}"
                for char, vp, target_faction in members_assigning_away
            ])
            embed.add_field(
                name="Members Assigning VPs Elsewhere",
                value=away_list,
                inline=False
            )

        # Assigned to faction
        if data['assigned_to_faction']:
            assigned_list = "\n".join([
                f"  {char.name}: {vp} VP"
                for char, vp in data['assigned_to_faction']
            ])
            assigned_total = sum(vp for _, vp in data['assigned_to_faction'])
            embed.add_field(
                name=f"VPs Assigned to {faction.name} ({assigned_total} VP)",
                value=assigned_list,
                inline=False
            )
    else:
        embed.add_field(
            name="Faction",
            value="Not a member of any faction",
            inline=False
        )

    return embed


def create_edit_unit_embed(unit: Unit, naval_positions: list = None) -> discord.Embed:
    """Create embed for editing unit via button interface."""
    embed = discord.Embed(
        title=f"Edit Unit: {unit.name or unit.unit_id}",
        description=f"Unit ID: `{unit.unit_id}`\nType: `{unit.unit_type}`",
        color=discord.Color.blue()
    )

    # Basic info
    embed.add_field(name="Status", value=unit.status, inline=True)
    embed.add_field(name="Territory", value=unit.current_territory_id or "None", inline=True)
    embed.add_field(name="Naval", value="Yes" if unit.is_naval else "No", inline=True)

    # Combat stats
    stats = f"Move: {unit.movement} | Org: {unit.organization}/{unit.max_organization}\n"
    stats += f"Atk: {unit.attack} | Def: {unit.defense}\n"
    stats += f"Siege Atk: {unit.siege_attack} | Siege Def: {unit.siege_defense}\n"
    stats += f"Size: {unit.size} | Capacity: {unit.capacity}"
    embed.add_field(name="Combat Stats", value=stats, inline=False)

    # Upkeep
    upkeep_parts = []
    if unit.upkeep_ore > 0:
        upkeep_parts.append(f"⛏️{unit.upkeep_ore}")
    if unit.upkeep_lumber > 0:
        upkeep_parts.append(f"🪵{unit.upkeep_lumber}")
    if unit.upkeep_coal > 0:
        upkeep_parts.append(f"⚫{unit.upkeep_coal}")
    if unit.upkeep_rations > 0:
        upkeep_parts.append(f"🍖{unit.upkeep_rations}")
    if unit.upkeep_cloth > 0:
        upkeep_parts.append(f"🧵{unit.upkeep_cloth}")
    if unit.upkeep_platinum > 0:
        upkeep_parts.append(f"🪙{unit.upkeep_platinum}")
    embed.add_field(name="Upkeep", value=" ".join(upkeep_parts) if upkeep_parts else "None", inline=False)

    # Keywords
    keywords = ", ".join(unit.keywords) if unit.keywords else "None"
    embed.add_field(name="Keywords", value=keywords, inline=False)

    # Naval positions (only for naval units)
    if unit.is_naval and naval_positions is not None:
        positions_str = ", ".join(naval_positions) if naval_positions else "None"
        embed.add_field(name="Naval Positions", value=positions_str, inline=False)

    embed.set_footer(text="Click a button to modify fields")
    return embed


def create_faction_victory_points_embed(data: dict) -> discord.Embed:
    """Create embed for faction victory points view (admin)."""
    faction = data['faction']

    embed = discord.Embed(
        title=f"Victory Points - {faction.name}",
        color=discord.Color.gold()
    )

    # Total VPs
    embed.add_field(
        name="Total Faction VPs",
        value=str(data['faction_total_vps']),
        inline=False
    )

    # Member breakdown (includes both territory VPs and character VPs)
    if data['faction_members_vps']:
        member_list = "\n".join([
            f"  {char.name}: {vp} VP"
            for char, vp in data['faction_members_vps']
        ])
        member_total = sum(vp for _, vp in data['faction_members_vps'])
        embed.add_field(
            name=f"Member VPs ({member_total} VP)",
            value=member_list,
            inline=False
        )
    else:
        embed.add_field(
            name="Member VPs",
            value="No members with victory points",
            inline=False
        )

    # Members assigning VPs elsewhere
    members_assigning_away = data.get('members_assigning_away', [])
    if members_assigning_away:
        away_list = "\n".join([
            f"  {char.name}: {vp} VP → {target_faction.name if target_faction else 'Unknown'}"
            for char, vp, target_faction in members_assigning_away
        ])
        embed.add_field(
            name="Members Assigning VPs Elsewhere",
            value=away_list,
            inline=False
        )

    # Assigned to faction
    if data['assigned_to_faction']:
        assigned_list = "\n".join([
            f"  {char.name}: {vp} VP"
            for char, vp in data['assigned_to_faction']
        ])
        assigned_total = sum(vp for _, vp in data['assigned_to_faction'])
        embed.add_field(
            name=f"Assigned VPs ({assigned_total} VP)",
            value=assigned_list,
            inline=False
        )
    else:
        embed.add_field(
            name="Assigned VPs",
            value="No VPs assigned to this faction",
            inline=False
        )

    return embed


def format_resource_totals(totals, show_zeros: bool = False) -> str:
    """
    Format resource totals as an emoji line.

    Args:
        totals: ResourceTotals object or dict with resource keys
        show_zeros: If True, show resources even if zero

    Returns:
        Formatted string like "⛏️ 5 | 🪵 3 | 🍖 2"
    """
    # Handle both ResourceTotals objects and dicts
    if hasattr(totals, 'to_dict'):
        values = totals.to_dict()
    else:
        values = totals

    parts = []
    resource_emojis = [
        ('ore', '⛏️'),
        ('lumber', '🪵'),
        ('coal', '⚫'),
        ('rations', '🍖'),
        ('cloth', '🧵'),
        ('platinum', '🪙')
    ]

    for key, emoji in resource_emojis:
        value = values.get(key, 0)
        if show_zeros or value != 0:
            parts.append(f"{emoji} {value}")

    return " | ".join(parts) if parts else "None"


def create_character_finances_embed(data: dict) -> discord.Embed:
    """Create a rich embed displaying character financial report."""
    character = data['character']

    embed = discord.Embed(
        title=f"Financial Report: {character.name}",
        description=f"Character: `{character.identifier}`",
        color=discord.Color.gold()
    )

    # Current Resources
    current = data['current_resources']
    embed.add_field(
        name="Current Resources",
        value=format_resource_totals(current, show_zeros=True),
        inline=False
    )

    # Personal Production
    personal_prod = data['personal_production']
    if not personal_prod.is_empty():
        embed.add_field(
            name="Personal Production",
            value=format_resource_totals(personal_prod),
            inline=False
        )
    else:
        embed.add_field(
            name="Personal Production",
            value="None",
            inline=False
        )

    # Territory Production
    territory_prod = data['territory_production']
    territory_count = data['territory_count']
    if territory_count > 0:
        embed.add_field(
            name=f"Territory Production ({territory_count} {'territory' if territory_count == 1 else 'territories'})",
            value=format_resource_totals(territory_prod) if not territory_prod.is_empty() else "None",
            inline=False
        )
    else:
        embed.add_field(
            name="Territory Production",
            value="No territories controlled",
            inline=False
        )

    # Building Production Bonuses
    building_prod = data.get('building_production')
    if building_prod and not building_prod.is_empty():
        embed.add_field(
            name="Building Production Bonuses",
            value=format_resource_totals(building_prod),
            inline=False
        )

    # Unit Upkeep
    unit_upkeep = data['unit_upkeep']
    unit_count = data['unit_count']
    if unit_count > 0:
        embed.add_field(
            name=f"Unit Upkeep ({unit_count} {'unit' if unit_count == 1 else 'units'})",
            value=format_resource_totals(unit_upkeep) if not unit_upkeep.is_empty() else "None",
            inline=False
        )
    else:
        embed.add_field(
            name="Unit Upkeep",
            value="No active units",
            inline=False
        )

    # Building Upkeep
    building_upkeep = data['building_upkeep']
    building_count = data['building_count']
    if building_count > 0:
        embed.add_field(
            name=f"Building Upkeep ({building_count} {'building' if building_count == 1 else 'buildings'})",
            value=format_resource_totals(building_upkeep) if not building_upkeep.is_empty() else "None",
            inline=False
        )
    else:
        embed.add_field(
            name="Building Upkeep",
            value="No active buildings",
            inline=False
        )

    # Outgoing Transfers
    outgoing = data['outgoing_transfers']
    transfer_count = data['transfer_count']
    if transfer_count > 0:
        embed.add_field(
            name=f"Outgoing Transfers ({transfer_count} {'transfer' if transfer_count == 1 else 'transfers'})",
            value=format_resource_totals(outgoing),
            inline=False
        )

    # Incoming Transfers
    incoming = data.get('incoming_transfers')
    incoming_count = data.get('incoming_transfer_count', 0)
    if incoming_count > 0:
        embed.add_field(
            name=f"Incoming Transfers ({incoming_count} {'transfer' if incoming_count == 1 else 'transfers'})",
            value=format_resource_totals(incoming),
            inline=False
        )

    # Net Resources (emphasized)
    net = data['net_resources']
    embed.add_field(
        name="**Net Resources (per turn)**",
        value=f"**{format_resource_totals(net, show_zeros=True)}**",
        inline=False
    )

    return embed


def create_faction_finances_embed(data: dict) -> discord.Embed:
    """Create a rich embed displaying faction financial report."""
    faction = data['faction']

    embed = discord.Embed(
        title=f"Financial Report: {faction.name}",
        description=f"Faction ID: `{faction.faction_id}`",
        color=discord.Color.gold()
    )

    # Current Resources (Treasury)
    current = data['current_resources']
    embed.add_field(
        name="Current Treasury",
        value=format_resource_totals(current, show_zeros=True),
        inline=False
    )

    # Territory Production
    territory_prod = data['territory_production']
    territory_count = data['territory_count']
    if territory_count > 0:
        embed.add_field(
            name=f"Territory Production ({territory_count} {'territory' if territory_count == 1 else 'territories'})",
            value=format_resource_totals(territory_prod) if not territory_prod.is_empty() else "None",
            inline=False
        )
    else:
        embed.add_field(
            name="Territory Production",
            value="No territories controlled",
            inline=False
        )

    # Building Production Bonuses
    building_prod = data.get('building_production')
    if building_prod and not building_prod.is_empty():
        embed.add_field(
            name="Building Production Bonuses",
            value=format_resource_totals(building_prod),
            inline=False
        )

    # Unit Upkeep
    unit_upkeep = data['unit_upkeep']
    unit_count = data['unit_count']
    if unit_count > 0:
        embed.add_field(
            name=f"Unit Upkeep ({unit_count} {'unit' if unit_count == 1 else 'units'})",
            value=format_resource_totals(unit_upkeep) if not unit_upkeep.is_empty() else "None",
            inline=False
        )
    else:
        embed.add_field(
            name="Unit Upkeep",
            value="No active faction-owned units",
            inline=False
        )

    # Building Upkeep
    building_upkeep = data['building_upkeep']
    building_count = data['building_count']
    if building_count > 0:
        embed.add_field(
            name=f"Building Upkeep ({building_count} {'building' if building_count == 1 else 'buildings'})",
            value=format_resource_totals(building_upkeep) if not building_upkeep.is_empty() else "None",
            inline=False
        )
    else:
        embed.add_field(
            name="Building Upkeep",
            value="No active buildings",
            inline=False
        )

    # Public Works Spending
    spending = data['spending_targets']
    if not spending.is_empty():
        embed.add_field(
            name="Public Works Spending",
            value=format_resource_totals(spending),
            inline=False
        )
    else:
        embed.add_field(
            name="Public Works Spending",
            value="None configured",
            inline=False
        )

    # Outgoing Transfers
    outgoing = data.get('outgoing_transfers')
    outgoing_count = data.get('outgoing_transfer_count', 0)
    if outgoing_count > 0:
        embed.add_field(
            name=f"Outgoing Transfers ({outgoing_count} {'transfer' if outgoing_count == 1 else 'transfers'})",
            value=format_resource_totals(outgoing),
            inline=False
        )

    # Incoming Transfers
    incoming = data.get('incoming_transfers')
    incoming_count = data.get('incoming_transfer_count', 0)
    if incoming_count > 0:
        embed.add_field(
            name=f"Incoming Transfers ({incoming_count} {'transfer' if incoming_count == 1 else 'transfers'})",
            value=format_resource_totals(incoming),
            inline=False
        )

    # Net Resources (emphasized)
    net = data['net_resources']
    embed.add_field(
        name="**Net Resources (per turn)**",
        value=f"**{format_resource_totals(net, show_zeros=True)}**",
        inline=False
    )

    return embed


def create_edit_unit_type_embed(unit_type: UnitType) -> discord.Embed:
    """Create embed for editing unit type via button interface."""
    embed = discord.Embed(
        title=f"Edit Unit Type: {unit_type.name}",
        description=f"Type ID: `{unit_type.type_id}`",
        color=discord.Color.blue()
    )

    # Basic info
    embed.add_field(name="Nation", value=unit_type.nation or "Any", inline=True)
    embed.add_field(name="Naval", value="Yes" if unit_type.is_naval else "No", inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=True)  # Spacer

    # Combat stats
    stats = f"Move: {unit_type.movement} | Org: {unit_type.organization}\n"
    stats += f"Atk: {unit_type.attack} | Def: {unit_type.defense}"
    embed.add_field(name="Combat Stats", value=stats, inline=False)

    # Size/Siege stats
    size_stats = f"Siege Atk: {unit_type.siege_attack} | Siege Def: {unit_type.siege_defense}\n"
    size_stats += f"Size: {unit_type.size} | Capacity: {unit_type.capacity}"
    embed.add_field(name="Size/Siege", value=size_stats, inline=False)

    # Cost
    cost_parts = []
    if unit_type.cost_ore > 0:
        cost_parts.append(f"\u26cf\ufe0f{unit_type.cost_ore}")
    if unit_type.cost_lumber > 0:
        cost_parts.append(f"\U0001fab5{unit_type.cost_lumber}")
    if unit_type.cost_coal > 0:
        cost_parts.append(f"\u26ab{unit_type.cost_coal}")
    if unit_type.cost_rations > 0:
        cost_parts.append(f"\U0001f356{unit_type.cost_rations}")
    if unit_type.cost_cloth > 0:
        cost_parts.append(f"\U0001f9f5{unit_type.cost_cloth}")
    if unit_type.cost_platinum > 0:
        cost_parts.append(f"\U0001fa99{unit_type.cost_platinum}")
    embed.add_field(name="Cost", value=" ".join(cost_parts) if cost_parts else "None", inline=True)

    # Upkeep
    upkeep_parts = []
    if unit_type.upkeep_ore > 0:
        upkeep_parts.append(f"\u26cf\ufe0f{unit_type.upkeep_ore}")
    if unit_type.upkeep_lumber > 0:
        upkeep_parts.append(f"\U0001fab5{unit_type.upkeep_lumber}")
    if unit_type.upkeep_coal > 0:
        upkeep_parts.append(f"\u26ab{unit_type.upkeep_coal}")
    if unit_type.upkeep_rations > 0:
        upkeep_parts.append(f"\U0001f356{unit_type.upkeep_rations}")
    if unit_type.upkeep_cloth > 0:
        upkeep_parts.append(f"\U0001f9f5{unit_type.upkeep_cloth}")
    if unit_type.upkeep_platinum > 0:
        upkeep_parts.append(f"\U0001fa99{unit_type.upkeep_platinum}")
    embed.add_field(name="Upkeep", value=" ".join(upkeep_parts) if upkeep_parts else "None", inline=True)

    # Keywords
    keywords = ", ".join(unit_type.keywords) if unit_type.keywords else "None"
    embed.add_field(name="Keywords", value=keywords, inline=False)

    embed.set_footer(text="Click a button to modify fields")
    return embed


def create_territory_counts_embed(data: List[dict]) -> discord.Embed:
    """Create embed displaying faction territory standings."""
    if len(data) == 1:
        title = f"Territory Standings — {data[0]['faction'].name}"
    else:
        title = "Territory Standings"
    embed = discord.Embed(
        title=title,
        color=discord.Color.dark_green()
    )

    # Build monospace table
    lines = []
    lines.append(f"{'Faction':<20} {'Now':>4} {'Start':>6} {'Delta':>6}")
    lines.append("-" * 38)

    for entry in data:
        faction = entry['faction']
        current = entry['current_count']
        starting = entry['starting_count']
        delta = current - starting
        if delta > 0:
            delta_str = f"+{delta}"
        elif delta == 0:
            delta_str = "0"
        else:
            delta_str = str(delta)

        name = faction.name
        if len(name) > 20:
            name = name[:17] + "..."
        lines.append(f"{name:<20} {current:>4} {starting:>6} {delta_str:>6}")

    embed.description = "```\n" + "\n".join(lines) + "\n```"

    return embed
