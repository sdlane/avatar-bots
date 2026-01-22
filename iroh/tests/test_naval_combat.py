"""
Pytest tests for naval combat phase in turn resolution.

Tests verify:
- Patrol units engage hostile units in overlapping territories
- Patrol units ignore allied and neutral fleets
- Non-patrol units don't initiate combat but participate when triggered
- Damage accumulates across multiple territories
- Combat resolution (attack > defense = 2 org damage per unit)
- Allied factions combine stats as one side
- Transport destruction leads to carried land units being destroyed
- Naval combat occurs before land combat in COMBAT phase
- Simultaneous damage application (units at 0 org still deal damage)

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_naval_combat.py -v
"""
import pytest
from datetime import datetime
from handlers.naval_combat_handlers import (
    execute_naval_combat_phase,
    find_naval_patrol_units,
    find_combat_territories_for_patrol,
    get_all_naval_units_in_territory,
    group_units_into_naval_combat_sides,
    calculate_naval_combat_damage_for_pairing,
    handle_transport_destruction,
    NavalCombatSide,
)
from handlers.turn_handlers import execute_combat_phase, disband_low_organization_units
from db import (
    Character, Unit, Territory, Order, WargameConfig, Faction, War, WarParticipant,
    Alliance, NavalUnitPosition
)
from order_types import OrderType, OrderStatus, TurnPhase
from tests.conftest import TEST_GUILD_ID


# ============================================================================
# Helper functions for test setup
# ============================================================================

async def create_factions_at_war(db_conn, faction_a_id: str, faction_b_id: str, war_id: str = "test-naval-war"):
    """Create two factions and put them at war."""
    faction_a = Faction(
        faction_id=faction_a_id, name=f"Faction {faction_a_id}",
        guild_id=TEST_GUILD_ID
    )
    await faction_a.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, faction_a_id, TEST_GUILD_ID)

    faction_b = Faction(
        faction_id=faction_b_id, name=f"Faction {faction_b_id}",
        guild_id=TEST_GUILD_ID
    )
    await faction_b.upsert(db_conn)
    faction_b = await Faction.fetch_by_faction_id(db_conn, faction_b_id, TEST_GUILD_ID)

    # Create war
    war = War(war_id=war_id, objective="Naval War", guild_id=TEST_GUILD_ID)
    await war.upsert(db_conn)
    war = await War.fetch_by_id(db_conn, war_id, TEST_GUILD_ID)

    # Add participants on opposite sides
    part_a = WarParticipant(
        war_id=war.id, faction_id=faction_a.id, side="SIDE_A", guild_id=TEST_GUILD_ID
    )
    await part_a.upsert(db_conn)

    part_b = WarParticipant(
        war_id=war.id, faction_id=faction_b.id, side="SIDE_B", guild_id=TEST_GUILD_ID
    )
    await part_b.upsert(db_conn)

    return faction_a, faction_b


async def create_allied_factions(db_conn, faction_a_id: str, faction_b_id: str, alliance_id: str = "test-alliance"):
    """Create two factions and form an alliance."""
    faction_a = Faction(
        faction_id=faction_a_id, name=f"Faction {faction_a_id}",
        guild_id=TEST_GUILD_ID
    )
    await faction_a.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, faction_a_id, TEST_GUILD_ID)

    faction_b = Faction(
        faction_id=faction_b_id, name=f"Faction {faction_b_id}",
        guild_id=TEST_GUILD_ID
    )
    await faction_b.upsert(db_conn)
    faction_b = await Faction.fetch_by_faction_id(db_conn, faction_b_id, TEST_GUILD_ID)

    # Alliance requires faction_a_id < faction_b_id for canonical ordering
    if faction_a.id < faction_b.id:
        a_id, b_id = faction_a.id, faction_b.id
    else:
        a_id, b_id = faction_b.id, faction_a.id

    # Create alliance
    alliance = Alliance(
        faction_a_id=a_id,
        faction_b_id=b_id,
        status="ACTIVE",
        initiated_by_faction_id=a_id,
        guild_id=TEST_GUILD_ID
    )
    await alliance.insert(db_conn)

    return faction_a, faction_b


async def create_naval_unit_with_patrol(db_conn, unit_id: str, faction, char, territory_ids: list,
                                         attack: int = 5, defense: int = 3, org: int = 10):
    """Create a naval unit with a patrol order and set positions."""
    unit = Unit(
        unit_id=unit_id, name=f"Naval Unit {unit_id}", unit_type="fleet",
        owner_character_id=char.id, faction_id=faction.id,
        movement=3, organization=org, max_organization=10,
        attack=attack, defense=defense,
        current_territory_id=territory_ids[0], is_naval=True,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, unit_id, TEST_GUILD_ID)

    # Set naval positions
    await NavalUnitPosition.set_positions(db_conn, unit.id, territory_ids, TEST_GUILD_ID)

    # Create patrol order
    order = Order(
        order_id=f"order-{unit_id}",
        order_type=OrderType.UNIT.value,
        status=OrderStatus.SUCCESS.value,
        phase=TurnPhase.MOVEMENT.value,
        unit_ids=[unit.id],
        order_data={'action': 'naval_patrol', 'path': territory_ids},
        character_id=char.id,
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    return unit


async def create_naval_unit_with_convoy(db_conn, unit_id: str, faction, char, territory_ids: list,
                                         attack: int = 5, defense: int = 3, org: int = 10):
    """Create a naval unit with a convoy order (not patrol)."""
    unit = Unit(
        unit_id=unit_id, name=f"Naval Unit {unit_id}", unit_type="fleet",
        owner_character_id=char.id, faction_id=faction.id,
        movement=3, organization=org, max_organization=10,
        attack=attack, defense=defense,
        current_territory_id=territory_ids[0], is_naval=True,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, unit_id, TEST_GUILD_ID)

    # Set naval positions
    await NavalUnitPosition.set_positions(db_conn, unit.id, territory_ids, TEST_GUILD_ID)

    # Create convoy order (not patrol)
    order = Order(
        order_id=f"order-{unit_id}",
        order_type=OrderType.UNIT.value,
        status=OrderStatus.SUCCESS.value,
        phase=TurnPhase.MOVEMENT.value,
        unit_ids=[unit.id],
        order_data={'action': 'naval_convoy', 'path': territory_ids},
        character_id=char.id,
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    return unit


async def create_naval_transport_with_cargo(db_conn, unit_id: str, faction, char, territory_ids: list,
                                             land_unit_ids: list, attack: int = 2, defense: int = 2, org: int = 10):
    """Create a naval transport with cargo aboard."""
    unit = Unit(
        unit_id=unit_id, name=f"Transport {unit_id}", unit_type="transport",
        owner_character_id=char.id, faction_id=faction.id,
        movement=3, organization=org, max_organization=10,
        attack=attack, defense=defense, capacity=5,
        current_territory_id=territory_ids[0], is_naval=True,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, unit_id, TEST_GUILD_ID)

    # Set naval positions
    await NavalUnitPosition.set_positions(db_conn, unit.id, territory_ids, TEST_GUILD_ID)

    # Create transport order with cargo
    order = Order(
        order_id=f"order-{unit_id}",
        order_type=OrderType.UNIT.value,
        status=OrderStatus.ONGOING.value,
        phase=TurnPhase.MOVEMENT.value,
        unit_ids=[unit.id],
        order_data={'action': 'naval_transport', 'path': territory_ids},
        result_data={'waiting_for_cargo': False, 'carrying_units': land_unit_ids},
        character_id=char.id,
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    return unit


# ============================================================================
# Basic Unit Tests
# ============================================================================

def test_calculate_naval_combat_damage_for_pairing():
    """Test organization damage calculation for naval combat."""
    # Attacker wins (attack > defense)
    attacker = NavalCombatSide()
    attacker.total_attack = 10
    attacker.total_defense = 5
    attacker.units = []

    unit1 = Unit(id=1, unit_id="fleet-1", status="ACTIVE")
    unit2 = Unit(id=2, unit_id="fleet-2", status="ACTIVE")
    defender = NavalCombatSide()
    defender.total_attack = 3
    defender.total_defense = 5  # 10 > 5, so defender takes 2 damage
    defender.units = [unit1, unit2]

    damage = calculate_naval_combat_damage_for_pairing(attacker, defender)
    assert damage == {1: 2, 2: 2}  # Both units take 2 damage

    # No damage when attack <= defense
    attacker.total_attack = 5
    damage = calculate_naval_combat_damage_for_pairing(attacker, defender)
    assert damage == {}

    # Attack exactly equal to defense - no damage
    attacker.total_attack = 5
    defender.total_defense = 5
    damage = calculate_naval_combat_damage_for_pairing(attacker, defender)
    assert damage == {}


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_patrol_engages_hostile_in_same_territory(db_conn, test_server):
    """Test that two hostile fleets in the same territory fight."""
    # Create characters
    char_a = Character(
        identifier="naval-char-a", name="Admiral A",
        channel_id=999100000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "naval-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="naval-char-b", name="Admiral B",
        channel_id=999100000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "naval-char-b", TEST_GUILD_ID)

    # Create factions at war
    faction_a, faction_b = await create_factions_at_war(db_conn, "navy-a", "navy-b")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create ocean territory
    ocean = Territory(territory_id="ocean-1", name="Ocean Zone 1", terrain_type="ocean", guild_id=TEST_GUILD_ID)
    await ocean.upsert(db_conn)

    # Create both fleets with patrol orders in same territory
    # Fleet A: attack=10, defense=5
    # Fleet B: attack=8, defense=4
    # A attacks B: 10 > 4 => B takes 2 damage
    # B attacks A: 8 > 5 => A takes 2 damage
    unit_a = await create_naval_unit_with_patrol(db_conn, "fleet-a", faction_a, char_a, ["ocean-1"],
                                                  attack=10, defense=5)
    unit_b = await create_naval_unit_with_patrol(db_conn, "fleet-b", faction_b, char_b, ["ocean-1"],
                                                  attack=8, defense=4)

    # Execute naval combat
    events = await execute_naval_combat_phase(db_conn, TEST_GUILD_ID, turn_number=1)

    # Verify combat events were generated
    event_types = [e.event_type for e in events]
    assert 'NAVAL_COMBAT_STARTED' in event_types
    assert 'NAVAL_COMBAT_DAMAGE' in event_types
    assert 'NAVAL_COMBAT_ENDED' in event_types

    # Verify damage was applied
    unit_a = await Unit.fetch_by_unit_id(db_conn, "fleet-a", TEST_GUILD_ID)
    unit_b = await Unit.fetch_by_unit_id(db_conn, "fleet-b", TEST_GUILD_ID)

    assert unit_a.organization == 8  # 10 - 2
    assert unit_b.organization == 8  # 10 - 2


@pytest.mark.asyncio
async def test_patrol_ignores_allied_fleet(db_conn, test_server):
    """Test that allied fleets don't fight each other."""
    # Create characters
    char_a = Character(
        identifier="allied-char-a", name="Allied Admiral A",
        channel_id=999100000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "allied-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="allied-char-b", name="Allied Admiral B",
        channel_id=999100000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "allied-char-b", TEST_GUILD_ID)

    # Create allied factions
    faction_a, faction_b = await create_allied_factions(db_conn, "allied-navy-a", "allied-navy-b")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create ocean territory
    ocean = Territory(territory_id="allied-ocean-1", name="Allied Ocean Zone", terrain_type="ocean", guild_id=TEST_GUILD_ID)
    await ocean.upsert(db_conn)

    # Create both fleets with patrol orders in same territory
    unit_a = await create_naval_unit_with_patrol(db_conn, "allied-fleet-a", faction_a, char_a, ["allied-ocean-1"])
    unit_b = await create_naval_unit_with_patrol(db_conn, "allied-fleet-b", faction_b, char_b, ["allied-ocean-1"])

    # Execute naval combat
    events = await execute_naval_combat_phase(db_conn, TEST_GUILD_ID, turn_number=1)

    # Should be no combat - allies don't fight
    event_types = [e.event_type for e in events]
    assert 'NAVAL_COMBAT_STARTED' not in event_types
    assert 'NAVAL_COMBAT_DAMAGE' not in event_types

    # Verify no damage
    unit_a = await Unit.fetch_by_unit_id(db_conn, "allied-fleet-a", TEST_GUILD_ID)
    unit_b = await Unit.fetch_by_unit_id(db_conn, "allied-fleet-b", TEST_GUILD_ID)

    assert unit_a.organization == 10  # No damage
    assert unit_b.organization == 10  # No damage


@pytest.mark.asyncio
async def test_patrol_ignores_neutral_fleet(db_conn, test_server):
    """Test that neutral (not at war) fleets don't fight."""
    # Create characters
    char_a = Character(
        identifier="neutral-char-a", name="Neutral Admiral A",
        channel_id=999100000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "neutral-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="neutral-char-b", name="Neutral Admiral B",
        channel_id=999100000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "neutral-char-b", TEST_GUILD_ID)

    # Create factions (NOT at war, NOT allied - just neutral)
    faction_a = Faction(faction_id="neutral-navy-a", name="Neutral Navy A", guild_id=TEST_GUILD_ID)
    await faction_a.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, "neutral-navy-a", TEST_GUILD_ID)

    faction_b = Faction(faction_id="neutral-navy-b", name="Neutral Navy B", guild_id=TEST_GUILD_ID)
    await faction_b.upsert(db_conn)
    faction_b = await Faction.fetch_by_faction_id(db_conn, "neutral-navy-b", TEST_GUILD_ID)

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create ocean territory
    ocean = Territory(territory_id="neutral-ocean-1", name="Neutral Ocean Zone", terrain_type="ocean", guild_id=TEST_GUILD_ID)
    await ocean.upsert(db_conn)

    # Create both fleets with patrol orders in same territory
    unit_a = await create_naval_unit_with_patrol(db_conn, "neutral-fleet-a", faction_a, char_a, ["neutral-ocean-1"])
    unit_b = await create_naval_unit_with_patrol(db_conn, "neutral-fleet-b", faction_b, char_b, ["neutral-ocean-1"])

    # Execute naval combat
    events = await execute_naval_combat_phase(db_conn, TEST_GUILD_ID, turn_number=1)

    # Should be no combat - neutral factions don't fight
    event_types = [e.event_type for e in events]
    assert 'NAVAL_COMBAT_STARTED' not in event_types

    # Verify no damage
    unit_a = await Unit.fetch_by_unit_id(db_conn, "neutral-fleet-a", TEST_GUILD_ID)
    unit_b = await Unit.fetch_by_unit_id(db_conn, "neutral-fleet-b", TEST_GUILD_ID)

    assert unit_a.organization == 10
    assert unit_b.organization == 10


@pytest.mark.asyncio
async def test_non_patrol_doesnt_initiate_combat(db_conn, test_server):
    """Test that convoy/transit units alone don't trigger combat."""
    # Create characters
    char_a = Character(
        identifier="convoy-char-a", name="Convoy Admiral A",
        channel_id=999100000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "convoy-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="convoy-char-b", name="Convoy Admiral B",
        channel_id=999100000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "convoy-char-b", TEST_GUILD_ID)

    # Create factions at war
    faction_a, faction_b = await create_factions_at_war(db_conn, "convoy-navy-a", "convoy-navy-b", "convoy-war")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create ocean territory
    ocean = Territory(territory_id="convoy-ocean-1", name="Convoy Ocean Zone", terrain_type="ocean", guild_id=TEST_GUILD_ID)
    await ocean.upsert(db_conn)

    # Create both fleets with CONVOY orders (not patrol) in same territory
    unit_a = await create_naval_unit_with_convoy(db_conn, "convoy-fleet-a", faction_a, char_a, ["convoy-ocean-1"])
    unit_b = await create_naval_unit_with_convoy(db_conn, "convoy-fleet-b", faction_b, char_b, ["convoy-ocean-1"])

    # Execute naval combat
    events = await execute_naval_combat_phase(db_conn, TEST_GUILD_ID, turn_number=1)

    # Should be no combat - convoy doesn't initiate
    event_types = [e.event_type for e in events]
    assert 'NAVAL_COMBAT_STARTED' not in event_types

    # Verify no damage
    unit_a = await Unit.fetch_by_unit_id(db_conn, "convoy-fleet-a", TEST_GUILD_ID)
    unit_b = await Unit.fetch_by_unit_id(db_conn, "convoy-fleet-b", TEST_GUILD_ID)

    assert unit_a.organization == 10
    assert unit_b.organization == 10


@pytest.mark.asyncio
async def test_convoy_participates_when_patrol_triggers(db_conn, test_server):
    """Test that convoy units participate when patrol triggers combat."""
    # Create characters
    char_a = Character(
        identifier="trigger-char-a", name="Trigger Admiral A",
        channel_id=999100000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "trigger-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="trigger-char-b", name="Trigger Admiral B",
        channel_id=999100000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "trigger-char-b", TEST_GUILD_ID)

    # Create factions at war
    faction_a, faction_b = await create_factions_at_war(db_conn, "trigger-navy-a", "trigger-navy-b", "trigger-war")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create ocean territory
    ocean = Territory(territory_id="trigger-ocean-1", name="Trigger Ocean Zone", terrain_type="ocean", guild_id=TEST_GUILD_ID)
    await ocean.upsert(db_conn)

    # Fleet A: patrol order (triggers combat), attack=10, defense=5
    # Fleet B: convoy order (participates once triggered), attack=6, defense=3
    # A attacks B: 10 > 3 => B takes 2 damage
    # B attacks A: 6 > 5 => A takes 2 damage
    unit_a = await create_naval_unit_with_patrol(db_conn, "trigger-patrol-a", faction_a, char_a, ["trigger-ocean-1"],
                                                  attack=10, defense=5)
    unit_b = await create_naval_unit_with_convoy(db_conn, "trigger-convoy-b", faction_b, char_b, ["trigger-ocean-1"],
                                                  attack=6, defense=3)

    # Execute naval combat
    events = await execute_naval_combat_phase(db_conn, TEST_GUILD_ID, turn_number=1)

    # Combat should occur
    event_types = [e.event_type for e in events]
    assert 'NAVAL_COMBAT_STARTED' in event_types
    assert 'NAVAL_COMBAT_DAMAGE' in event_types

    # Verify both took damage
    unit_a = await Unit.fetch_by_unit_id(db_conn, "trigger-patrol-a", TEST_GUILD_ID)
    unit_b = await Unit.fetch_by_unit_id(db_conn, "trigger-convoy-b", TEST_GUILD_ID)

    assert unit_a.organization == 8  # 10 - 2
    assert unit_b.organization == 8  # 10 - 2


@pytest.mark.asyncio
async def test_damage_accumulates_across_territories(db_conn, test_server):
    """Test that a unit in multiple combats takes cumulative damage."""
    # Create characters
    char_a = Character(
        identifier="multi-char-a", name="Multi Admiral A",
        channel_id=999100000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "multi-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="multi-char-b", name="Multi Admiral B",
        channel_id=999100000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "multi-char-b", TEST_GUILD_ID)

    # Create factions at war
    faction_a, faction_b = await create_factions_at_war(db_conn, "multi-navy-a", "multi-navy-b", "multi-war")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create 3 ocean territories
    for i in range(1, 4):
        ocean = Territory(territory_id=f"multi-ocean-{i}", name=f"Multi Ocean Zone {i}", terrain_type="ocean", guild_id=TEST_GUILD_ID)
        await ocean.upsert(db_conn)

    # Fleet A: patrol across all 3 territories, attack=10, defense=10
    # Fleet B: patrol in territory 1 only, attack=20, defense=1
    # Fleet C: patrol in territory 2 only, attack=20, defense=1
    # Fleet D: patrol in territory 3 only, attack=20, defense=1
    # Fleet A fights in all 3 territories, takes 2 damage from each = 6 total damage
    unit_a = await create_naval_unit_with_patrol(db_conn, "multi-fleet-a", faction_a, char_a,
                                                  ["multi-ocean-1", "multi-ocean-2", "multi-ocean-3"],
                                                  attack=10, defense=10)

    # Enemy fleets in each territory
    unit_b = await create_naval_unit_with_patrol(db_conn, "multi-fleet-b", faction_b, char_b, ["multi-ocean-1"],
                                                  attack=20, defense=1)

    # Need another character for more enemy units
    char_c = Character(
        identifier="multi-char-c", name="Multi Admiral C",
        channel_id=999100000000000003, guild_id=TEST_GUILD_ID
    )
    await char_c.upsert(db_conn)
    char_c = await Character.fetch_by_identifier(db_conn, "multi-char-c", TEST_GUILD_ID)
    char_c.represented_faction_id = faction_b.id
    await char_c.upsert(db_conn)

    unit_c = await create_naval_unit_with_patrol(db_conn, "multi-fleet-c", faction_b, char_c, ["multi-ocean-2"],
                                                  attack=20, defense=1)

    char_d = Character(
        identifier="multi-char-d", name="Multi Admiral D",
        channel_id=999100000000000004, guild_id=TEST_GUILD_ID
    )
    await char_d.upsert(db_conn)
    char_d = await Character.fetch_by_identifier(db_conn, "multi-char-d", TEST_GUILD_ID)
    char_d.represented_faction_id = faction_b.id
    await char_d.upsert(db_conn)

    unit_d = await create_naval_unit_with_patrol(db_conn, "multi-fleet-d", faction_b, char_d, ["multi-ocean-3"],
                                                  attack=20, defense=1)

    # Execute naval combat
    events = await execute_naval_combat_phase(db_conn, TEST_GUILD_ID, turn_number=1)

    # Verify Fleet A took 6 damage (2 from each of 3 combats)
    unit_a = await Unit.fetch_by_unit_id(db_conn, "multi-fleet-a", TEST_GUILD_ID)
    assert unit_a.organization == 4  # 10 - 6 (2 damage from each of 3 combats)

    # The enemy fleets each took 2 damage (Fleet A's attack=10 > their defense=1)
    unit_b = await Unit.fetch_by_unit_id(db_conn, "multi-fleet-b", TEST_GUILD_ID)
    unit_c = await Unit.fetch_by_unit_id(db_conn, "multi-fleet-c", TEST_GUILD_ID)
    unit_d = await Unit.fetch_by_unit_id(db_conn, "multi-fleet-d", TEST_GUILD_ID)

    assert unit_b.organization == 8
    assert unit_c.organization == 8
    assert unit_d.organization == 8


@pytest.mark.asyncio
async def test_allied_factions_combined_stats(db_conn, test_server):
    """Test that allied factions combine attack/defense stats against enemy."""
    # Create characters
    char_a = Character(
        identifier="combined-char-a", name="Combined Admiral A",
        channel_id=999100000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "combined-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="combined-char-b", name="Combined Admiral B",
        channel_id=999100000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "combined-char-b", TEST_GUILD_ID)

    char_enemy = Character(
        identifier="combined-char-enemy", name="Enemy Admiral",
        channel_id=999100000000000003, guild_id=TEST_GUILD_ID
    )
    await char_enemy.upsert(db_conn)
    char_enemy = await Character.fetch_by_identifier(db_conn, "combined-char-enemy", TEST_GUILD_ID)

    # Create allied factions
    faction_a, faction_b = await create_allied_factions(db_conn, "combined-ally-a", "combined-ally-b", "combined-alliance")

    # Create enemy faction
    faction_enemy = Faction(faction_id="combined-enemy", name="Combined Enemy", guild_id=TEST_GUILD_ID)
    await faction_enemy.upsert(db_conn)
    faction_enemy = await Faction.fetch_by_faction_id(db_conn, "combined-enemy", TEST_GUILD_ID)

    # Put enemy at war with faction_a (alliance means also at war with faction_b)
    war = War(war_id="combined-war", objective="Combined War", guild_id=TEST_GUILD_ID)
    await war.upsert(db_conn)
    war = await War.fetch_by_id(db_conn, "combined-war", TEST_GUILD_ID)

    part_a = WarParticipant(war_id=war.id, faction_id=faction_a.id, side="SIDE_A", guild_id=TEST_GUILD_ID)
    await part_a.upsert(db_conn)
    part_b = WarParticipant(war_id=war.id, faction_id=faction_b.id, side="SIDE_A", guild_id=TEST_GUILD_ID)
    await part_b.upsert(db_conn)
    part_enemy = WarParticipant(war_id=war.id, faction_id=faction_enemy.id, side="SIDE_B", guild_id=TEST_GUILD_ID)
    await part_enemy.upsert(db_conn)

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)
    char_enemy.represented_faction_id = faction_enemy.id
    await char_enemy.upsert(db_conn)

    # Create ocean territory
    ocean = Territory(territory_id="combined-ocean-1", name="Combined Ocean Zone", terrain_type="ocean", guild_id=TEST_GUILD_ID)
    await ocean.upsert(db_conn)

    # Allied fleets: A has attack=5, B has attack=5 (combined=10)
    # Enemy fleet: defense=8
    # Combined attack (10) > enemy defense (8), so enemy takes damage
    # Enemy attack=12, allied combined defense = 3+3=6
    # Enemy attack (12) > allied defense (6), so allies take damage
    unit_a = await create_naval_unit_with_patrol(db_conn, "combined-ally-fleet-a", faction_a, char_a, ["combined-ocean-1"],
                                                  attack=5, defense=3)
    unit_b = await create_naval_unit_with_patrol(db_conn, "combined-ally-fleet-b", faction_b, char_b, ["combined-ocean-1"],
                                                  attack=5, defense=3)
    unit_enemy = await create_naval_unit_with_patrol(db_conn, "combined-enemy-fleet", faction_enemy, char_enemy, ["combined-ocean-1"],
                                                      attack=12, defense=8)

    # Execute naval combat
    events = await execute_naval_combat_phase(db_conn, TEST_GUILD_ID, turn_number=1)

    # Verify combat occurred
    event_types = [e.event_type for e in events]
    assert 'NAVAL_COMBAT_STARTED' in event_types

    # Verify damage
    unit_a = await Unit.fetch_by_unit_id(db_conn, "combined-ally-fleet-a", TEST_GUILD_ID)
    unit_b = await Unit.fetch_by_unit_id(db_conn, "combined-ally-fleet-b", TEST_GUILD_ID)
    unit_enemy = await Unit.fetch_by_unit_id(db_conn, "combined-enemy-fleet", TEST_GUILD_ID)

    # Both allies should take 2 damage (enemy attack=12 > combined defense=6)
    assert unit_a.organization == 8  # 10 - 2
    assert unit_b.organization == 8  # 10 - 2
    # Enemy should take 2 damage (combined attack=10 > enemy defense=8)
    assert unit_enemy.organization == 8  # 10 - 2


@pytest.mark.asyncio
async def test_transport_destroyed_cargo_destroyed(db_conn, test_server):
    """Test that land units are destroyed when their transport is destroyed."""
    # Create characters
    char_a = Character(
        identifier="transport-char-a", name="Transport Admiral A",
        channel_id=999100000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "transport-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="transport-char-b", name="Transport Admiral B",
        channel_id=999100000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "transport-char-b", TEST_GUILD_ID)

    # Create factions at war
    faction_a, faction_b = await create_factions_at_war(db_conn, "transport-navy-a", "transport-navy-b", "transport-war")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create ocean territory
    ocean = Territory(territory_id="transport-ocean-1", name="Transport Ocean Zone", terrain_type="ocean", guild_id=TEST_GUILD_ID)
    await ocean.upsert(db_conn)

    # Create land unit being transported
    land_unit = Unit(
        unit_id="transported-infantry", name="Transported Infantry", unit_type="infantry",
        owner_character_id=char_a.id, faction_id=faction_a.id,
        movement=2, organization=10, max_organization=10,
        attack=3, defense=3,
        current_territory_id="transport-ocean-1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await land_unit.upsert(db_conn)
    land_unit = await Unit.fetch_by_unit_id(db_conn, "transported-infantry", TEST_GUILD_ID)

    # Create transport with low org (will be destroyed)
    # Transport: org=2, so after taking 2 damage will be at 0
    transport = await create_naval_transport_with_cargo(
        db_conn, "transport-a", faction_a, char_a, ["transport-ocean-1"],
        land_unit_ids=[land_unit.id], attack=1, defense=1, org=2
    )

    # Create enemy fleet with high attack
    enemy_fleet = await create_naval_unit_with_patrol(db_conn, "transport-enemy", faction_b, char_b, ["transport-ocean-1"],
                                                       attack=10, defense=10)

    # Execute naval combat
    events = await execute_naval_combat_phase(db_conn, TEST_GUILD_ID, turn_number=1)

    # Verify transport took damage and is at 0 or below
    transport = await Unit.fetch_by_unit_id(db_conn, "transport-a", TEST_GUILD_ID)
    assert transport.organization <= 0

    # Verify TRANSPORT_CARGO_DESTROYED event was generated
    event_types = [e.event_type for e in events]
    assert 'TRANSPORT_CARGO_DESTROYED' in event_types

    # Verify land unit was destroyed
    land_unit = await Unit.fetch_by_unit_id(db_conn, "transported-infantry", TEST_GUILD_ID)
    assert land_unit.status == 'DISBANDED'


@pytest.mark.asyncio
async def test_unit_at_zero_org_still_deals_damage(db_conn, test_server):
    """Test that units reaching 0 org still deal damage (simultaneous resolution)."""
    # Create characters
    char_a = Character(
        identifier="simul-char-a", name="Simultaneous Admiral A",
        channel_id=999100000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "simul-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="simul-char-b", name="Simultaneous Admiral B",
        channel_id=999100000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "simul-char-b", TEST_GUILD_ID)

    # Create factions at war
    faction_a, faction_b = await create_factions_at_war(db_conn, "simul-navy-a", "simul-navy-b", "simul-war")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create ocean territory
    ocean = Territory(territory_id="simul-ocean-1", name="Simultaneous Ocean Zone", terrain_type="ocean", guild_id=TEST_GUILD_ID)
    await ocean.upsert(db_conn)

    # Both fleets have low org (2) and will be destroyed
    # But both should still deal damage to each other (simultaneous)
    # Fleet A: attack=10, defense=1, org=2
    # Fleet B: attack=10, defense=1, org=2
    # Both attack > other's defense, so both take 2 damage = 0 org
    unit_a = await create_naval_unit_with_patrol(db_conn, "simul-fleet-a", faction_a, char_a, ["simul-ocean-1"],
                                                  attack=10, defense=1, org=2)
    unit_b = await create_naval_unit_with_patrol(db_conn, "simul-fleet-b", faction_b, char_b, ["simul-ocean-1"],
                                                  attack=10, defense=1, org=2)

    # Execute naval combat
    events = await execute_naval_combat_phase(db_conn, TEST_GUILD_ID, turn_number=1)

    # Both should have taken damage (simultaneous resolution)
    unit_a = await Unit.fetch_by_unit_id(db_conn, "simul-fleet-a", TEST_GUILD_ID)
    unit_b = await Unit.fetch_by_unit_id(db_conn, "simul-fleet-b", TEST_GUILD_ID)

    assert unit_a.organization == 0  # 2 - 2
    assert unit_b.organization == 0  # 2 - 2

    # Check damage events - both should have received damage
    damage_events = [e for e in events if e.event_type == 'NAVAL_COMBAT_DAMAGE']
    assert len(damage_events) == 2


@pytest.mark.asyncio
async def test_transport_destroyed_in_org_phase(db_conn, test_server):
    """Test that land units are destroyed when transport is disbanded in org phase."""
    # Create characters
    char_a = Character(
        identifier="org-transport-char-a", name="Org Transport Admiral A",
        channel_id=999100000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "org-transport-char-a", TEST_GUILD_ID)

    # Create faction
    faction_a = Faction(faction_id="org-transport-navy-a", name="Org Transport Navy A", guild_id=TEST_GUILD_ID)
    await faction_a.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, "org-transport-navy-a", TEST_GUILD_ID)

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)

    # Create ocean territory
    ocean = Territory(territory_id="org-transport-ocean-1", name="Org Transport Ocean Zone", terrain_type="ocean", guild_id=TEST_GUILD_ID)
    await ocean.upsert(db_conn)

    # Create land unit being transported
    land_unit = Unit(
        unit_id="org-transported-infantry", name="Org Transported Infantry", unit_type="infantry",
        owner_character_id=char_a.id, faction_id=faction_a.id,
        movement=2, organization=10, max_organization=10,
        attack=3, defense=3,
        current_territory_id="org-transport-ocean-1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await land_unit.upsert(db_conn)
    land_unit = await Unit.fetch_by_unit_id(db_conn, "org-transported-infantry", TEST_GUILD_ID)

    # Create transport with org=0 (will be disbanded in org phase)
    transport = await create_naval_transport_with_cargo(
        db_conn, "org-transport-a", faction_a, char_a, ["org-transport-ocean-1"],
        land_unit_ids=[land_unit.id], attack=1, defense=1, org=0
    )

    # Execute disband (org phase)
    events = await disband_low_organization_units(db_conn, TEST_GUILD_ID, turn_number=1, phase=TurnPhase.ORGANIZATION.value)

    # Verify transport was disbanded
    transport = await Unit.fetch_by_unit_id(db_conn, "org-transport-a", TEST_GUILD_ID)
    assert transport.status == 'DISBANDED'

    # Verify land unit was also destroyed
    land_unit = await Unit.fetch_by_unit_id(db_conn, "org-transported-infantry", TEST_GUILD_ID)
    assert land_unit.status == 'DISBANDED'

    # Verify TRANSPORT_CARGO_DESTROYED event was generated
    event_types = [e.event_type for e in events]
    assert 'TRANSPORT_CARGO_DESTROYED' in event_types


@pytest.mark.asyncio
async def test_no_patrol_units_no_combat(db_conn, test_server):
    """Test that no combat occurs when there are no patrol units."""
    # Create characters
    char_a = Character(
        identifier="nopatrol-char-a", name="NoPatrol Admiral A",
        channel_id=999100000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "nopatrol-char-a", TEST_GUILD_ID)

    # Create faction
    faction_a = Faction(faction_id="nopatrol-navy-a", name="NoPatrol Navy A", guild_id=TEST_GUILD_ID)
    await faction_a.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, "nopatrol-navy-a", TEST_GUILD_ID)

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)

    # Create ocean territory
    ocean = Territory(territory_id="nopatrol-ocean-1", name="NoPatrol Ocean Zone", terrain_type="ocean", guild_id=TEST_GUILD_ID)
    await ocean.upsert(db_conn)

    # Create fleet with convoy order only (no patrol)
    unit_a = await create_naval_unit_with_convoy(db_conn, "nopatrol-fleet-a", faction_a, char_a, ["nopatrol-ocean-1"])

    # Execute naval combat
    events = await execute_naval_combat_phase(db_conn, TEST_GUILD_ID, turn_number=1)

    # No combat should occur
    assert len(events) == 0

    # Verify no damage
    unit_a = await Unit.fetch_by_unit_id(db_conn, "nopatrol-fleet-a", TEST_GUILD_ID)
    assert unit_a.organization == 10


@pytest.mark.asyncio
async def test_combat_phase_runs_naval_before_land(db_conn, test_server):
    """Test that naval combat runs before land combat in execute_combat_phase."""
    # This is an integration test to verify the combat phase ordering
    # Setup naval combat
    char_a = Character(
        identifier="phase-char-a", name="Phase Admiral A",
        channel_id=999100000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "phase-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="phase-char-b", name="Phase Admiral B",
        channel_id=999100000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "phase-char-b", TEST_GUILD_ID)

    # Create factions at war
    faction_a, faction_b = await create_factions_at_war(db_conn, "phase-navy-a", "phase-navy-b", "phase-war")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create ocean territory
    ocean = Territory(territory_id="phase-ocean-1", name="Phase Ocean Zone", terrain_type="ocean", guild_id=TEST_GUILD_ID)
    await ocean.upsert(db_conn)

    # Create both fleets with patrol orders
    unit_a = await create_naval_unit_with_patrol(db_conn, "phase-fleet-a", faction_a, char_a, ["phase-ocean-1"],
                                                  attack=10, defense=5)
    unit_b = await create_naval_unit_with_patrol(db_conn, "phase-fleet-b", faction_b, char_b, ["phase-ocean-1"],
                                                  attack=8, defense=4)

    # Execute full combat phase (which should run naval then land)
    events = await execute_combat_phase(db_conn, TEST_GUILD_ID, turn_number=1)

    # Verify naval combat events exist
    event_types = [e.event_type for e in events]
    assert 'NAVAL_COMBAT_STARTED' in event_types
    assert 'NAVAL_COMBAT_DAMAGE' in event_types
    assert 'NAVAL_COMBAT_ENDED' in event_types
