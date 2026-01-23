"""
Finance handler functions for viewing character and faction financial reports.
"""
import asyncpg
from dataclasses import dataclass
from typing import Optional, Tuple, List
from db import (
    Character, Faction, FactionMember, FactionPermission, FactionResources,
    Territory, Unit, Building, Order, PlayerResources
)
from handlers.turn_handlers import calculate_building_production_bonus


@dataclass
class ResourceTotals:
    """Represents totals for each resource type."""
    ore: int = 0
    lumber: int = 0
    coal: int = 0
    rations: int = 0
    cloth: int = 0
    platinum: int = 0

    def add(self, other: "ResourceTotals") -> "ResourceTotals":
        """Add another ResourceTotals to this one and return a new instance."""
        return ResourceTotals(
            ore=self.ore + other.ore,
            lumber=self.lumber + other.lumber,
            coal=self.coal + other.coal,
            rations=self.rations + other.rations,
            cloth=self.cloth + other.cloth,
            platinum=self.platinum + other.platinum
        )

    def subtract(self, other: "ResourceTotals") -> "ResourceTotals":
        """Subtract another ResourceTotals from this one and return a new instance."""
        return ResourceTotals(
            ore=self.ore - other.ore,
            lumber=self.lumber - other.lumber,
            coal=self.coal - other.coal,
            rations=self.rations - other.rations,
            cloth=self.cloth - other.cloth,
            platinum=self.platinum - other.platinum
        )

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            'ore': self.ore,
            'lumber': self.lumber,
            'coal': self.coal,
            'rations': self.rations,
            'cloth': self.cloth,
            'platinum': self.platinum
        }

    def is_empty(self) -> bool:
        """Check if all values are zero."""
        return (self.ore == 0 and self.lumber == 0 and self.coal == 0 and
                self.rations == 0 and self.cloth == 0 and self.platinum == 0)


async def get_character_finances(
    conn: asyncpg.Connection,
    character_id: int,
    guild_id: int
) -> Tuple[bool, str, Optional[dict]]:
    """
    Get comprehensive financial report for a character.

    Returns:
        (success, message, data) where data contains:
        - character: Character object
        - current_resources: ResourceTotals of current inventory
        - personal_production: ResourceTotals from character's base production
        - territory_production: ResourceTotals from controlled territories
        - territory_count: Number of controlled territories
        - unit_upkeep: ResourceTotals from owned units (ACTIVE only)
        - unit_count: Number of ACTIVE units
        - building_upkeep: ResourceTotals from buildings in controlled territories
        - building_count: Number of ACTIVE buildings
        - outgoing_transfers: ResourceTotals from ONGOING resource transfer orders
        - transfer_count: Number of outgoing transfers
        - net_resources: ResourceTotals (production - expenses)
    """
    character = await Character.fetch_by_id(conn, character_id)
    if not character:
        return False, "Character not found.", None

    # Fetch current resources
    resources = await PlayerResources.fetch_by_character(conn, character_id, guild_id)
    if resources:
        current_resources = ResourceTotals(
            ore=resources.ore,
            lumber=resources.lumber,
            coal=resources.coal,
            rations=resources.rations,
            cloth=resources.cloth,
            platinum=resources.platinum
        )
    else:
        current_resources = ResourceTotals()

    # Personal production from character fields
    personal_production = ResourceTotals(
        ore=character.ore_production,
        lumber=character.lumber_production,
        coal=character.coal_production,
        rations=character.rations_production,
        cloth=character.cloth_production,
        platinum=character.platinum_production
    )

    # Territory production
    territories = await Territory.fetch_by_controller(conn, character_id, guild_id)
    territory_production = ResourceTotals()
    for t in territories:
        territory_production.ore += t.ore_production
        territory_production.lumber += t.lumber_production
        territory_production.coal += t.coal_production
        territory_production.rations += t.rations_production
        territory_production.cloth += t.cloth_production
        territory_production.platinum += t.platinum_production

    # Building production bonuses
    building_production = ResourceTotals()
    for t in territories:
        bonus = await calculate_building_production_bonus(conn, t, guild_id)
        building_production.ore += bonus.get('ore', 0)
        building_production.lumber += bonus.get('lumber', 0)
        building_production.coal += bonus.get('coal', 0)
        building_production.rations += bonus.get('rations', 0)
        building_production.cloth += bonus.get('cloth', 0)
        building_production.platinum += bonus.get('platinum', 0)

    # Unit upkeep (ACTIVE only)
    units = await Unit.fetch_by_owner(conn, character_id, guild_id)
    active_units = [u for u in units if u.status == 'ACTIVE']
    unit_upkeep = ResourceTotals()
    for u in active_units:
        unit_upkeep.ore += u.upkeep_ore
        unit_upkeep.lumber += u.upkeep_lumber
        unit_upkeep.coal += u.upkeep_coal
        unit_upkeep.rations += u.upkeep_rations
        unit_upkeep.cloth += u.upkeep_cloth
        unit_upkeep.platinum += u.upkeep_platinum

    # Building upkeep (ACTIVE buildings in controlled territories)
    building_upkeep = ResourceTotals()
    building_count = 0
    for t in territories:
        buildings = await Building.fetch_by_territory(conn, t.territory_id, guild_id)
        active_buildings = [b for b in buildings if b.status == 'ACTIVE']
        building_count += len(active_buildings)
        for b in active_buildings:
            building_upkeep.ore += b.upkeep_ore
            building_upkeep.lumber += b.upkeep_lumber
            building_upkeep.coal += b.upkeep_coal
            building_upkeep.rations += b.upkeep_rations
            building_upkeep.cloth += b.upkeep_cloth
            building_upkeep.platinum += b.upkeep_platinum

    # Outgoing resource transfers (ONGOING orders)
    transfer_orders = await Order.fetch_by_character_and_type(
        conn, character_id, guild_id, 'RESOURCE_TRANSFER', 'ONGOING'
    )
    outgoing_transfers = ResourceTotals()
    for order in transfer_orders:
        order_data = order.order_data or {}
        outgoing_transfers.ore += order_data.get('ore', 0)
        outgoing_transfers.lumber += order_data.get('lumber', 0)
        outgoing_transfers.coal += order_data.get('coal', 0)
        outgoing_transfers.rations += order_data.get('rations', 0)
        outgoing_transfers.cloth += order_data.get('cloth', 0)
        outgoing_transfers.platinum += order_data.get('platinum', 0)

    # Calculate total production and expenses
    total_production = personal_production.add(territory_production).add(building_production)
    total_expenses = unit_upkeep.add(building_upkeep).add(outgoing_transfers)
    net_resources = total_production.subtract(total_expenses)

    return True, "", {
        'character': character,
        'current_resources': current_resources,
        'personal_production': personal_production,
        'territory_production': territory_production,
        'building_production': building_production,
        'territory_count': len(territories),
        'unit_upkeep': unit_upkeep,
        'unit_count': len(active_units),
        'building_upkeep': building_upkeep,
        'building_count': building_count,
        'outgoing_transfers': outgoing_transfers,
        'transfer_count': len(transfer_orders),
        'net_resources': net_resources
    }


async def get_faction_finances(
    conn: asyncpg.Connection,
    faction_id: int,
    guild_id: int
) -> Tuple[bool, str, Optional[dict]]:
    """
    Get comprehensive financial report for a faction.

    Returns:
        (success, message, data) where data contains:
        - faction: Faction object
        - current_resources: ResourceTotals of faction treasury
        - territory_production: ResourceTotals from faction-controlled territories
        - territory_count: Number of faction-controlled territories
        - unit_upkeep: ResourceTotals from faction-owned units (ACTIVE only)
        - unit_count: Number of ACTIVE faction-owned units
        - building_upkeep: ResourceTotals from buildings in faction territories
        - building_count: Number of ACTIVE buildings
        - spending_targets: ResourceTotals from faction spending configuration
        - net_resources: ResourceTotals (production - expenses)
    """
    faction = await Faction.fetch_by_id(conn, faction_id)
    if not faction:
        return False, "Faction not found.", None

    # Fetch current faction resources (treasury)
    resources = await FactionResources.fetch_by_faction(conn, faction_id, guild_id)
    if resources:
        current_resources = ResourceTotals(
            ore=resources.ore,
            lumber=resources.lumber,
            coal=resources.coal,
            rations=resources.rations,
            cloth=resources.cloth,
            platinum=resources.platinum
        )
    else:
        current_resources = ResourceTotals()

    # Territory production (faction-controlled territories)
    territories = await Territory.fetch_by_faction_controller(conn, faction_id, guild_id)
    territory_production = ResourceTotals()
    for t in territories:
        territory_production.ore += t.ore_production
        territory_production.lumber += t.lumber_production
        territory_production.coal += t.coal_production
        territory_production.rations += t.rations_production
        territory_production.cloth += t.cloth_production
        territory_production.platinum += t.platinum_production

    # Building production bonuses
    building_production = ResourceTotals()
    for t in territories:
        bonus = await calculate_building_production_bonus(conn, t, guild_id)
        building_production.ore += bonus.get('ore', 0)
        building_production.lumber += bonus.get('lumber', 0)
        building_production.coal += bonus.get('coal', 0)
        building_production.rations += bonus.get('rations', 0)
        building_production.cloth += bonus.get('cloth', 0)
        building_production.platinum += bonus.get('platinum', 0)

    # Unit upkeep (faction-owned units, ACTIVE only)
    units = await Unit.fetch_by_faction_owner(conn, faction_id, guild_id)
    active_units = [u for u in units if u.status == 'ACTIVE']
    unit_upkeep = ResourceTotals()
    for u in active_units:
        unit_upkeep.ore += u.upkeep_ore
        unit_upkeep.lumber += u.upkeep_lumber
        unit_upkeep.coal += u.upkeep_coal
        unit_upkeep.rations += u.upkeep_rations
        unit_upkeep.cloth += u.upkeep_cloth
        unit_upkeep.platinum += u.upkeep_platinum

    # Building upkeep (ACTIVE buildings in faction territories)
    building_upkeep = ResourceTotals()
    building_count = 0
    for t in territories:
        buildings = await Building.fetch_by_territory(conn, t.territory_id, guild_id)
        active_buildings = [b for b in buildings if b.status == 'ACTIVE']
        building_count += len(active_buildings)
        for b in active_buildings:
            building_upkeep.ore += b.upkeep_ore
            building_upkeep.lumber += b.upkeep_lumber
            building_upkeep.coal += b.upkeep_coal
            building_upkeep.rations += b.upkeep_rations
            building_upkeep.cloth += b.upkeep_cloth
            building_upkeep.platinum += b.upkeep_platinum

    # Spending targets from faction configuration
    spending_targets = ResourceTotals(
        ore=faction.ore_spending,
        lumber=faction.lumber_spending,
        coal=faction.coal_spending,
        rations=faction.rations_spending,
        cloth=faction.cloth_spending,
        platinum=faction.platinum_spending
    )

    # Calculate net resources
    total_production = territory_production.add(building_production)
    total_expenses = unit_upkeep.add(building_upkeep).add(spending_targets)
    net_resources = total_production.subtract(total_expenses)

    return True, "", {
        'faction': faction,
        'current_resources': current_resources,
        'territory_production': territory_production,
        'building_production': building_production,
        'territory_count': len(territories),
        'unit_upkeep': unit_upkeep,
        'unit_count': len(active_units),
        'building_upkeep': building_upkeep,
        'building_count': building_count,
        'spending_targets': spending_targets,
        'net_resources': net_resources
    }


async def view_character_finances(
    conn: asyncpg.Connection,
    user_id: int,
    guild_id: int
) -> Tuple[bool, str, Optional[dict]]:
    """
    View financial report for the user's character.

    Returns:
        (success, message, data) - data from get_character_finances()
    """
    character = await Character.fetch_by_user(conn, user_id, guild_id)
    if not character:
        return False, "You don't have a character assigned. Ask a GM to assign you one using hawky.", None

    return await get_character_finances(conn, character.id, guild_id)


async def view_faction_finances(
    conn: asyncpg.Connection,
    user_id: int,
    guild_id: int
) -> Tuple[bool, str, Optional[dict]]:
    """
    View financial report for the user's represented faction.
    Requires FINANCIAL permission or being the faction leader.

    Returns:
        (success, message, data) - data from get_faction_finances()
    """
    character = await Character.fetch_by_user(conn, user_id, guild_id)
    if not character:
        return False, "You don't have a character assigned. Ask a GM to assign you one using hawky.", None

    # Check for represented faction first
    faction = None
    if character.represented_faction_id:
        faction = await Faction.fetch_by_id(conn, character.represented_faction_id)

    # Fall back to faction membership
    if not faction:
        faction_member = await FactionMember.fetch_by_character(conn, character.id, guild_id)
        if faction_member:
            faction = await Faction.fetch_by_id(conn, faction_member.faction_id)

    if not faction:
        return False, f"{character.name} is not a member of any faction.", None

    # Check if user is faction leader or has FINANCIAL permission
    is_leader = faction.leader_character_id == character.id
    has_financial = await FactionPermission.has_permission(
        conn, faction.id, character.id, 'FINANCIAL', guild_id
    )

    if not is_leader and not has_financial:
        return False, f"{character.name} does not have permission to view {faction.name}'s finances. You need to be the faction leader or have FINANCIAL permission.", None

    return await get_faction_finances(conn, faction.id, guild_id)


async def admin_view_finances(
    conn: asyncpg.Connection,
    identifier: str,
    guild_id: int
) -> Tuple[bool, str, Optional[dict]]:
    """
    Admin view of financial report for a character or faction.

    Args:
        conn: Database connection
        identifier: Character identifier or faction_id to look up
        guild_id: Guild ID

    Returns:
        (success, message, data) where data contains:
        - entity_type: 'character' or 'faction'
        - All data from get_character_finances() or get_faction_finances()
    """
    # Try character first
    character = await Character.fetch_by_identifier(conn, identifier, guild_id)
    if character:
        success, message, data = await get_character_finances(conn, character.id, guild_id)
        if success:
            data['entity_type'] = 'character'
        return success, message, data

    # Try faction
    faction = await Faction.fetch_by_faction_id(conn, identifier, guild_id)
    if faction:
        success, message, data = await get_faction_finances(conn, faction.id, guild_id)
        if success:
            data['entity_type'] = 'faction'
        return success, message, data

    return False, f"No character or faction found with identifier '{identifier}'.", None
