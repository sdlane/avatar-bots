"""
Helper functions for creating rich Discord embeds for wargame data display.
"""
import discord
from typing import List, Optional, Tuple
from db import (
    Territory, Faction, Unit, UnitType, PlayerResources,
    WargameConfig, Character, FactionMember
)


def create_territory_embed(territory: Territory, adjacent_ids: List[int], controller_name: Optional[str] = None) -> discord.Embed:
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

    # Adjacent territories
    if adjacent_ids:
        embed.add_field(
            name="Adjacent Territories",
            value=", ".join(str(tid) for tid in sorted(adjacent_ids)),
            inline=False
        )

    return embed


def create_faction_embed(faction: Faction, members: List[Character], leader: Optional[Character] = None) -> discord.Embed:
    """Create a rich embed displaying faction information."""
    embed = discord.Embed(
        title=f"⚔️ {faction.name}",
        description=f"Faction ID: `{faction.faction_id}`",
        color=discord.Color.red()
    )

    # Leader
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

    return embed


def create_unit_embed(unit: Unit, unit_type: Optional[UnitType] = None, owner: Optional[Character] = None,
                      commander: Optional[Character] = None, faction: Optional[Faction] = None,
                      show_full_details: bool = True) -> discord.Embed:
    """Create a rich embed displaying unit information."""
    embed = discord.Embed(
        title=f"🎖️ {unit.name or unit.unit_id}",
        description=f"Unit ID: `{unit.unit_id}` | Type: {unit.unit_type}",
        color=discord.Color.blue()
    )

    # Ownership info (only for admins)
    if show_full_details:
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

    # Location
    if unit.current_territory_id is not None:
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

    # Stats (only for admins)
    if show_full_details:
        stats_lines = [
            f"**Movement:** {unit.movement}",
            f"**Organization:** {unit.organization}/{unit.max_organization}",
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

        # Upkeep (only for admins)
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

        # Keywords (only for admins)
        if unit.keywords:
            embed.add_field(
                name="Keywords",
                value=", ".join(unit.keywords),
                inline=False
            )
    else:
        # Limited info for non-admins
        embed.add_field(
            name="Information",
            value="Full unit details are only visible to server administrators.",
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


def create_victory_points_embed(data: dict) -> discord.Embed:
    """Create embed for victory points view."""
    character = data['character']

    embed = discord.Embed(
        title=f"Victory Points - {character.name}",
        color=discord.Color.gold()
    )

    # Personal VPs
    personal_vps = data['personal_vps']
    if data['territories']:
        territory_list = "\n".join([
            f"  {t.name or f'Territory {t.territory_id}'}: {vp} VP"
            for t, vp in data['territories']
        ])
        embed.add_field(
            name=f"Your Territories ({personal_vps} VP)",
            value=territory_list,
            inline=False
        )
    else:
        embed.add_field(
            name="Your Territories",
            value=f"No territories with victory points ({personal_vps} VP total)",
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

    # Member breakdown
    if data['faction_members_vps']:
        member_list = "\n".join([
            f"  {char.name}: {vp} VP"
            for char, vp in data['faction_members_vps']
        ])
        member_total = sum(vp for _, vp in data['faction_members_vps'])
        embed.add_field(
            name=f"Member Territories ({member_total} VP)",
            value=member_list,
            inline=False
        )
    else:
        embed.add_field(
            name="Member Territories",
            value="No members with victory point territories",
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
