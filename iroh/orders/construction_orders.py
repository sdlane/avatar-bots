"""
Construction phase order handlers for mobilization and building construction.
"""
from order_types import OrderType, OrderStatus, TurnPhase
from datetime import datetime
from db import (
    Order, Character, Faction, FactionMember, Territory, TurnLog,
    Unit, UnitType, Building, BuildingType, PlayerResources, FactionResources,
    Alliance, FactionPermission
)
from handlers.spirit_nexus_handlers import (
    apply_industrial_damage,
    building_type_is_industrial,
    apply_spiritual_repair,
    building_type_is_spiritual,
)
import asyncpg
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

# Nation prefix map for unit ID generation
NATION_PREFIX_MAP = {
    'fire-nation': 'FN',
    'earth-kingdom': 'EK',
    'north-water': 'NW',
    'south-water': 'SW',
    'water-tribe': 'WT',
    'air-nomads': 'AN',
    'fifth-nation': '5N',
}


async def generate_unit_id(conn: asyncpg.Connection, nation: Optional[str], guild_id: int) -> str:
    """
    Generate a unique unit ID using nation prefix pattern.

    Args:
        conn: Database connection
        nation: Nation identifier (e.g., 'fire-nation')
        guild_id: Guild ID

    Returns:
        Unit ID like "FN-001", "EK-002", "5N-003"
    """
    prefix = NATION_PREFIX_MAP.get(nation, 'UN') if nation else 'UN'

    # Query max existing number for this prefix
    result = await conn.fetchval("""
        SELECT COALESCE(MAX(
            CASE
                WHEN unit_id ~ ('^' || $1 || '-[0-9]+$')
                THEN CAST(SUBSTRING(unit_id FROM LENGTH($1) + 2) AS INTEGER)
                ELSE 0
            END
        ), 0)
        FROM Unit WHERE guild_id = $2;
    """, prefix, guild_id)

    next_num = (result or 0) + 1
    return f"{prefix}-{next_num:03d}"


async def _is_territory_accessible_for_construction(
    conn: asyncpg.Connection,
    territory: Territory,
    faction_id: int,
    guild_id: int
) -> bool:
    """
    Check if territory is controlled by the faction or a member of the faction.

    Args:
        conn: Database connection
        territory: Territory to check
        faction_id: Faction ID (internal)
        guild_id: Guild ID

    Returns:
        True if territory is accessible, False otherwise
    """
    # Check if territory is controlled by the faction directly
    if territory.controller_faction_id == faction_id:
        return True

    # Check if territory is controlled by a character who is a member of the faction
    if territory.controller_character_id:
        member = await FactionMember.fetch_by_character(
            conn, territory.controller_character_id, guild_id
        )
        if member and member.faction_id == faction_id:
            return True

    return False


async def handle_mobilization_order(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Handle a MOBILIZATION order to create a new unit.

    Args:
        conn: Database connection
        order: The order to process
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    try:
        # Extract order data
        unit_type_id = order.order_data.get('unit_type_id')
        territory_id = order.order_data.get('territory_id')
        faction_id = order.order_data.get('faction_id')
        unit_name = order.order_data.get('unit_name')
        use_faction_resources = order.order_data.get('use_faction_resources', False)

        # Validate character still exists
        character = await Character.fetch_by_id(conn, order.character_id)
        if not character:
            return await _fail_mobilization_order(conn, order, guild_id, turn_number, 'Character not found')

        # Validate unit type still exists
        unit_type = await UnitType.fetch_by_type_id(conn, unit_type_id, guild_id)
        if not unit_type:
            return await _fail_mobilization_order(conn, order, guild_id, turn_number, f'Unit type {unit_type_id} not found')

        # Validate territory still exists
        territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
        if not territory:
            return await _fail_mobilization_order(conn, order, guild_id, turn_number, f'Territory {territory_id} not found')

        # Re-validate territory control for faction mobilization
        target_faction = None
        if faction_id:
            target_faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
            if not target_faction:
                return await _fail_mobilization_order(conn, order, guild_id, turn_number, f'Faction {faction_id} not found')

            # Re-check territory is controlled by faction or a faction member
            territory_accessible = await _is_territory_accessible_for_construction(
                conn, territory, target_faction.id, guild_id
            )
            if not territory_accessible:
                return await _fail_mobilization_order(
                    conn, order, guild_id, turn_number,
                    f'Territory {territory_id} is no longer controlled by {target_faction.name} or a member of the faction'
                )

        # Get faction nation for nation matching validation
        submitter_membership = await FactionMember.fetch_by_character(conn, order.character_id, guild_id)
        submitter_faction = None
        submitter_faction_nation = None

        if submitter_membership:
            submitter_faction = await Faction.fetch_by_id(conn, submitter_membership.faction_id)
            if submitter_faction:
                submitter_faction_nation = submitter_faction.nation

        # Re-validate nation matching rules
        if unit_type.nation:
            owner_nation = target_faction.nation if target_faction else submitter_faction_nation

            if owner_nation != unit_type.nation:
                return await _fail_mobilization_order(
                    conn, order, guild_id, turn_number,
                    f'Unit type requires nation {unit_type.nation} but faction is {owner_nation or "none"}'
                )

            # Fifth Nation exception: can build Fifth Nation units anywhere they control
            is_fifth_nation_exception = (owner_nation == "fifth-nation" and unit_type.nation == "fifth-nation")

            if not is_fifth_nation_exception:
                if territory.original_nation != unit_type.nation:
                    return await _fail_mobilization_order(
                        conn, order, guild_id, turn_number,
                        f'Unit type can only be built in {unit_type.nation} territories'
                    )

        # Calculate cost
        cost = {
            'ore': unit_type.cost_ore,
            'lumber': unit_type.cost_lumber,
            'coal': unit_type.cost_coal,
            'rations': unit_type.cost_rations,
            'cloth': unit_type.cost_cloth,
            'platinum': unit_type.cost_platinum
        }

        # Check and deduct resources
        if use_faction_resources and target_faction:
            resources = await FactionResources.fetch_by_faction(conn, target_faction.id, guild_id)
            if not resources:
                resources = FactionResources(
                    faction_id=target_faction.id,
                    ore=0, lumber=0, coal=0, rations=0, cloth=0, platinum=0,
                    guild_id=guild_id
                )
        else:
            resources = await PlayerResources.fetch_by_character(conn, order.character_id, guild_id)
            if not resources:
                resources = PlayerResources(
                    character_id=order.character_id,
                    ore=0, lumber=0, coal=0, rations=0, cloth=0, platinum=0,
                    guild_id=guild_id
                )

        # Check if sufficient resources
        insufficient = []
        for resource_type, needed in cost.items():
            available = getattr(resources, resource_type, 0)
            if available < needed:
                insufficient.append(f"{resource_type}: need {needed}, have {available}")

        if insufficient:
            return await _fail_mobilization_order(
                conn, order, guild_id, turn_number,
                f'Insufficient resources: {", ".join(insufficient)}'
            )

        # Deduct resources
        for resource_type, needed in cost.items():
            current = getattr(resources, resource_type)
            setattr(resources, resource_type, current - needed)
        await resources.upsert(conn)

        # Generate unit ID
        owner_nation = target_faction.nation if target_faction else submitter_faction_nation
        new_unit_id = await generate_unit_id(conn, owner_nation or unit_type.nation, guild_id)

        # Determine ownership
        if use_faction_resources and target_faction:
            owner_character_id = None
            owner_faction_id = target_faction.id
            faction_id_for_unit = target_faction.id
        else:
            owner_character_id = order.character_id
            owner_faction_id = None
            faction_id_for_unit = submitter_faction.id if submitter_faction else None

        # Create unit
        unit = Unit(
            unit_id=new_unit_id,
            name=unit_name,
            unit_type=unit_type.type_id,
            owner_character_id=owner_character_id,
            owner_faction_id=owner_faction_id,
            commander_character_id=order.character_id,
            commander_assigned_turn=turn_number,
            faction_id=faction_id_for_unit,
            movement=unit_type.movement,
            organization=unit_type.organization,
            max_organization=unit_type.organization,
            attack=unit_type.attack,
            defense=unit_type.defense,
            siege_attack=unit_type.siege_attack,
            siege_defense=unit_type.siege_defense,
            size=unit_type.size,
            capacity=unit_type.capacity,
            current_territory_id=territory_id,
            is_naval=unit_type.is_naval,
            upkeep_ore=unit_type.upkeep_ore,
            upkeep_lumber=unit_type.upkeep_lumber,
            upkeep_coal=unit_type.upkeep_coal,
            upkeep_rations=unit_type.upkeep_rations,
            upkeep_cloth=unit_type.upkeep_cloth,
            upkeep_platinum=unit_type.upkeep_platinum,
            keywords=unit_type.keywords,
            guild_id=guild_id,
            status='ACTIVE'
        )
        await unit.upsert(conn)

        # Mark order as success
        order.status = OrderStatus.SUCCESS.value
        order.result_data = {
            'unit_id': new_unit_id,
            'unit_name': unit_name or new_unit_id,
            'unit_type': unit_type.name,
            'territory_id': territory_id,
            'cost': cost
        }
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)

        # Build affected character IDs
        affected_ids = [order.character_id]
        if use_faction_resources and target_faction:
            # Add faction members with CONSTRUCTION permission
            construction_holders = await FactionPermission.fetch_characters_with_permission(
                conn, target_faction.id, "CONSTRUCTION", guild_id
            )
            for char_id in construction_holders:
                if char_id not in affected_ids:
                    affected_ids.append(char_id)

        logger.info(f"Mobilization: Created unit {new_unit_id} ({unit_type.name}) in territory {territory_id}")

        return [TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.CONSTRUCTION.value,
            event_type='UNIT_MOBILIZED',
            entity_type='unit',
            entity_id=unit.id,
            event_data={
                'unit_id': new_unit_id,
                'unit_name': unit_name or new_unit_id,
                'unit_type': unit_type.name,
                'territory_id': territory_id,
                'cost': cost,
                'order_id': order.order_id,
                'character_name': character.name,
                'faction_name': target_faction.name if target_faction else None,
                'affected_character_ids': affected_ids
            },
            guild_id=guild_id
        )]

    except Exception as e:
        logger.error(f"Error processing mobilization order {order.order_id}: {e}")
        return await _fail_mobilization_order(conn, order, guild_id, turn_number, str(e))


async def _fail_mobilization_order(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int,
    turn_number: int,
    error: str
) -> List[TurnLog]:
    """Mark a MOBILIZATION order as failed and return failure event."""
    order.status = OrderStatus.FAILED.value
    order.result_data = {'error': error}
    order.updated_at = datetime.now()
    order.updated_turn = turn_number
    await order.upsert(conn)

    logger.warning(f"Mobilization order {order.order_id} failed: {error}")

    return [TurnLog(
        turn_number=turn_number,
        phase=TurnPhase.CONSTRUCTION.value,
        event_type='MOBILIZATION_FAILED',
        entity_type='character',
        entity_id=order.character_id,
        event_data={
            'order_type': 'MOBILIZATION',
            'order_id': order.order_id,
            'error': error,
            'affected_character_ids': [order.character_id]
        },
        guild_id=guild_id
    )]


async def handle_construction_order(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int,
    turn_number: int
) -> List[TurnLog]:
    """
    Handle a CONSTRUCTION order to build a new building.

    Args:
        conn: Database connection
        order: The order to process
        guild_id: Guild ID
        turn_number: Current turn number

    Returns:
        List of TurnLog objects
    """
    try:
        # Extract order data
        building_type_id = order.order_data.get('building_type_id')
        territory_id = order.order_data.get('territory_id')
        faction_id = order.order_data.get('faction_id')
        use_faction_resources = order.order_data.get('use_faction_resources', False)

        # Validate character still exists
        character = await Character.fetch_by_id(conn, order.character_id)
        if not character:
            return await _fail_construction_order(conn, order, guild_id, turn_number, 'Character not found')

        # Validate building type still exists
        building_type = await BuildingType.fetch_by_type_id(conn, building_type_id, guild_id)
        if not building_type:
            return await _fail_construction_order(conn, order, guild_id, turn_number, f'Building type {building_type_id} not found')

        # Validate territory still exists
        territory = await Territory.fetch_by_territory_id(conn, territory_id, guild_id)
        if not territory:
            return await _fail_construction_order(conn, order, guild_id, turn_number, f'Territory {territory_id} not found')

        # Check for sacred-land keyword - cannot construct on sacred land
        if territory.keywords and 'sacred-land' in [k.lower() for k in territory.keywords]:
            return await _fail_construction_order(
                conn, order, guild_id, turn_number,
                f"Territory {territory_id} has sacred-land keyword and cannot have buildings constructed"
            )

        # Get target faction if using faction resources
        target_faction = None
        if faction_id:
            target_faction = await Faction.fetch_by_faction_id(conn, faction_id, guild_id)
            if not target_faction:
                return await _fail_construction_order(conn, order, guild_id, turn_number, f'Faction {faction_id} not found')

        # Calculate cost
        cost = {
            'ore': building_type.cost_ore,
            'lumber': building_type.cost_lumber,
            'coal': building_type.cost_coal,
            'rations': building_type.cost_rations,
            'cloth': building_type.cost_cloth,
            'platinum': building_type.cost_platinum
        }

        # Check and deduct resources
        if use_faction_resources and target_faction:
            resources = await FactionResources.fetch_by_faction(conn, target_faction.id, guild_id)
            if not resources:
                resources = FactionResources(
                    faction_id=target_faction.id,
                    ore=0, lumber=0, coal=0, rations=0, cloth=0, platinum=0,
                    guild_id=guild_id
                )
        else:
            resources = await PlayerResources.fetch_by_character(conn, order.character_id, guild_id)
            if not resources:
                resources = PlayerResources(
                    character_id=order.character_id,
                    ore=0, lumber=0, coal=0, rations=0, cloth=0, platinum=0,
                    guild_id=guild_id
                )

        # Check if sufficient resources
        insufficient = []
        for resource_type, needed in cost.items():
            available = getattr(resources, resource_type, 0)
            if available < needed:
                insufficient.append(f"{resource_type}: need {needed}, have {available}")

        if insufficient:
            return await _fail_construction_order(
                conn, order, guild_id, turn_number,
                f'Insufficient resources: {", ".join(insufficient)}'
            )

        # Deduct resources
        for resource_type, needed in cost.items():
            current = getattr(resources, resource_type)
            setattr(resources, resource_type, current - needed)
        await resources.upsert(conn)

        # Generate building ID
        building_count = await conn.fetchval(
            "SELECT COUNT(*) FROM Building WHERE guild_id = $1;",
            guild_id
        )
        new_building_id = f"BLD-{(building_count or 0) + 1:04d}"

        # Create building
        building = Building(
            building_id=new_building_id,
            name=building_type.name,
            building_type=building_type.type_id,
            territory_id=territory_id,
            durability=10,  # Default durability
            status='ACTIVE',
            upkeep_ore=building_type.upkeep_ore,
            upkeep_lumber=building_type.upkeep_lumber,
            upkeep_coal=building_type.upkeep_coal,
            upkeep_rations=building_type.upkeep_rations,
            upkeep_cloth=building_type.upkeep_cloth,
            upkeep_platinum=building_type.upkeep_platinum,
            guild_id=guild_id
        )
        await building.upsert(conn)

        # Check for industrial damage to spirit nexuses
        nexus_damage_log = None
        if building_type_is_industrial(building_type):
            nexus_damage_log = await apply_industrial_damage(
                conn=conn,
                territory_id=territory_id,
                guild_id=guild_id,
                turn_number=turn_number,
                building_type_name=building_type.name,
                building_id=new_building_id
            )

        # Check for spiritual repair to spirit nexuses
        nexus_repair_log = None
        if building_type_is_spiritual(building_type):
            nexus_repair_log = await apply_spiritual_repair(
                conn=conn,
                territory_id=territory_id,
                guild_id=guild_id,
                turn_number=turn_number,
                building_type_name=building_type.name,
                building_id=new_building_id
            )

        # Mark order as success
        order.status = OrderStatus.SUCCESS.value
        order.result_data = {
            'building_id': new_building_id,
            'building_type': building_type.name,
            'territory_id': territory_id,
            'cost': cost
        }
        order.updated_at = datetime.now()
        order.updated_turn = turn_number
        await order.upsert(conn)

        # Build affected character IDs
        affected_ids = [order.character_id]
        if use_faction_resources and target_faction:
            # Add faction members with CONSTRUCTION permission
            construction_holders = await FactionPermission.fetch_characters_with_permission(
                conn, target_faction.id, "CONSTRUCTION", guild_id
            )
            for char_id in construction_holders:
                if char_id not in affected_ids:
                    affected_ids.append(char_id)

        logger.info(f"Construction: Created building {new_building_id} ({building_type.name}) in territory {territory_id}")

        logs = [TurnLog(
            turn_number=turn_number,
            phase=TurnPhase.CONSTRUCTION.value,
            event_type='BUILDING_CONSTRUCTED',
            entity_type='building',
            entity_id=building.id,
            event_data={
                'building_id': new_building_id,
                'building_type': building_type.name,
                'territory_id': territory_id,
                'cost': cost,
                'order_id': order.order_id,
                'character_name': character.name,
                'faction_name': target_faction.name if target_faction else None,
                'affected_character_ids': affected_ids
            },
            guild_id=guild_id
        )]

        # Add nexus damage log if present (GM-only event)
        if nexus_damage_log:
            logs.append(nexus_damage_log)

        # Add nexus repair log if present (GM-only event)
        if nexus_repair_log:
            logs.append(nexus_repair_log)

        return logs

    except Exception as e:
        logger.error(f"Error processing construction order {order.order_id}: {e}")
        return await _fail_construction_order(conn, order, guild_id, turn_number, str(e))


async def _fail_construction_order(
    conn: asyncpg.Connection,
    order: Order,
    guild_id: int,
    turn_number: int,
    error: str
) -> List[TurnLog]:
    """Mark a CONSTRUCTION order as failed and return failure event."""
    order.status = OrderStatus.FAILED.value
    order.result_data = {'error': error}
    order.updated_at = datetime.now()
    order.updated_turn = turn_number
    await order.upsert(conn)

    logger.warning(f"Construction order {order.order_id} failed: {error}")

    return [TurnLog(
        turn_number=turn_number,
        phase=TurnPhase.CONSTRUCTION.value,
        event_type='CONSTRUCTION_FAILED',
        entity_type='character',
        entity_id=order.character_id,
        event_data={
            'order_type': 'CONSTRUCTION',
            'order_id': order.order_id,
            'error': error,
            'affected_character_ids': [order.character_id]
        },
        guild_id=guild_id
    )]
