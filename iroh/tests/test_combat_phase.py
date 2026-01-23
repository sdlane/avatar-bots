"""
Pytest tests for the land combat phase in turn resolution.

Tests verify:
- Basic combat (two factions at war, one side retreats)
- Organization damage (attack > defense causes -2 org per unit)
- No damage when attack <= defense
- Unit disbandment when org <= 0
- Retreat mechanics (along original path, toward capital, or any safe territory)
- Multi-faction combat (3+ sides, all pairs fight before disbandment)
- Territory capture (rural only, not cities)
- Building durability damage on capture
- Action-based hostility (capture vs capture, raid vs capture, raid vs raid)
- Max rounds safety limit

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_combat_phase.py -v
"""
import pytest
from datetime import datetime
from handlers.combat_handlers import (
    execute_combat_phase,
    find_combat_territories,
    group_units_into_sides,
    detect_action_conflicts,
    are_factions_hostile_for_combat,
    calculate_org_damage_for_pairing,
    determine_retreating_side_for_pairing,
    resolve_territory_capture,
    CombatSide,
)
from db import (
    Character, Unit, Territory, Order, WargameConfig, Faction, War, WarParticipant,
    Alliance, Building, FactionMember, TerritoryAdjacency
)
from order_types import OrderType, OrderStatus, TurnPhase, ORDER_PRIORITY_MAP
from tests.conftest import TEST_GUILD_ID


# ============================================================================
# Helper functions for test setup
# ============================================================================

async def create_faction_at_war(db_conn, faction_a_id: str, faction_b_id: str, war_id: str = "test-war"):
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
    war = War(war_id=war_id, objective="Test War", guild_id=TEST_GUILD_ID)
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


# ============================================================================
# Basic Unit Tests
# ============================================================================

def test_detect_action_conflicts():
    """Test action conflict detection for neutral factions."""
    # Conflicting pairs
    assert detect_action_conflicts('capture', 'capture') == True
    assert detect_action_conflicts('capture', 'raid') == True
    assert detect_action_conflicts('raid', 'capture') == True
    assert detect_action_conflicts('raid', 'raid') == True

    # Non-conflicting
    assert detect_action_conflicts('capture', 'transit') == False
    assert detect_action_conflicts('transit', 'patrol') == False
    assert detect_action_conflicts(None, 'capture') == False
    assert detect_action_conflicts('capture', None) == False
    assert detect_action_conflicts(None, None) == False


def test_calculate_org_damage_for_pairing():
    """Test organization damage calculation for a single pairing."""
    # Attacker wins (attack > defense)
    attacker = CombatSide()
    attacker.total_attack = 10
    attacker.total_defense = 5
    attacker.units = []

    unit1 = Unit(id=1, unit_id="u1", status="ACTIVE")
    unit2 = Unit(id=2, unit_id="u2", status="ACTIVE")
    defender = CombatSide()
    defender.total_attack = 3
    defender.total_defense = 5  # 10 > 5, so defender takes damage
    defender.units = [unit1, unit2]

    damage = calculate_org_damage_for_pairing(attacker, defender)
    assert damage == {1: 2, 2: 2}  # Both units take 2 damage

    # No damage when attack <= defense
    attacker.total_attack = 5
    damage = calculate_org_damage_for_pairing(attacker, defender)
    assert damage == {}


def test_determine_retreating_side_for_pairing():
    """Test retreat determination between two sides."""
    side_a = CombatSide()
    side_a.total_attack = 10
    side_a.faction_ids = {1}

    side_b = CombatSide()
    side_b.total_attack = 5
    side_b.faction_ids = {2}

    # Lower attack retreats
    retreating = determine_retreating_side_for_pairing(side_a, side_b, None)
    assert retreating == side_b

    # Tie goes to controller
    side_b.total_attack = 10
    retreating = determine_retreating_side_for_pairing(side_a, side_b, 1)  # faction 1 controls
    assert retreating == side_b  # side_a is controller, stays

    retreating = determine_retreating_side_for_pairing(side_a, side_b, 2)  # faction 2 controls
    assert retreating == side_a  # side_b is controller, stays

    # Tie with no controller
    retreating = determine_retreating_side_for_pairing(side_a, side_b, None)
    assert retreating is None  # No retreat on tie without controller


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_find_combat_territories_with_war(db_conn, test_server):
    """Test finding territories with hostile units at war."""
    # Create characters for each faction
    char_a = Character(
        identifier="combat-char-a", name="Fighter A",
        channel_id=999100000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "combat-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="combat-char-b", name="Fighter B",
        channel_id=999100000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "combat-char-b", TEST_GUILD_ID)

    # Create factions and put them at war
    faction_a, faction_b = await create_faction_at_war(db_conn, "faction-combat-a", "faction-combat-b")

    # Set characters to represent factions
    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)

    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create territory
    t1 = Territory(territory_id="COMBAT-T1", name="Combat Territory", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)

    # Create units from opposing factions in the same territory
    unit_a = Unit(
        unit_id="combat-unit-a", name="Unit A", unit_type="infantry",
        owner_character_id=char_a.id, faction_id=faction_a.id,
        movement=2, organization=10, max_organization=10,
        attack=5, defense=3,
        current_territory_id="COMBAT-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_a.upsert(db_conn)

    unit_b = Unit(
        unit_id="combat-unit-b", name="Unit B", unit_type="infantry",
        owner_character_id=char_b.id, faction_id=faction_b.id,
        movement=2, organization=10, max_organization=10,
        attack=4, defense=4,
        current_territory_id="COMBAT-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_b.upsert(db_conn)

    # Find combat territories
    combat_territories = await find_combat_territories(db_conn, TEST_GUILD_ID)
    assert "COMBAT-T1" in combat_territories


@pytest.mark.asyncio
async def test_no_combat_without_hostility(db_conn, test_server):
    """Test that no combat occurs between non-hostile factions."""
    # Create characters
    char_a = Character(
        identifier="peace-char-a", name="Peaceful A",
        channel_id=999110000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "peace-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="peace-char-b", name="Peaceful B",
        channel_id=999110000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "peace-char-b", TEST_GUILD_ID)

    # Create factions but NOT at war
    faction_a = Faction(faction_id="peace-faction-a", name="Peaceful Faction A", guild_id=TEST_GUILD_ID)
    await faction_a.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, "peace-faction-a", TEST_GUILD_ID)

    faction_b = Faction(faction_id="peace-faction-b", name="Peaceful Faction B", guild_id=TEST_GUILD_ID)
    await faction_b.upsert(db_conn)
    faction_b = await Faction.fetch_by_faction_id(db_conn, "peace-faction-b", TEST_GUILD_ID)

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)

    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create territory
    t1 = Territory(territory_id="PEACE-T1", name="Peaceful Territory", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)

    # Create units in same territory
    unit_a = Unit(
        unit_id="peace-unit-a", unit_type="infantry",
        owner_character_id=char_a.id, faction_id=faction_a.id,
        movement=2, organization=10, max_organization=10,
        attack=5, defense=3,
        current_territory_id="PEACE-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_a.upsert(db_conn)

    unit_b = Unit(
        unit_id="peace-unit-b", unit_type="infantry",
        owner_character_id=char_b.id, faction_id=faction_b.id,
        movement=2, organization=10, max_organization=10,
        attack=4, defense=4,
        current_territory_id="PEACE-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_b.upsert(db_conn)

    # Find combat territories - should be empty
    combat_territories = await find_combat_territories(db_conn, TEST_GUILD_ID)
    assert "PEACE-T1" not in combat_territories


@pytest.mark.asyncio
async def test_basic_combat_one_side_retreats(db_conn, test_server):
    """Test basic combat where one side retreats due to lower attack."""
    # Setup characters
    char_a = Character(
        identifier="retreat-char-a", name="Strong Fighter",
        channel_id=999120000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "retreat-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="retreat-char-b", name="Weak Fighter",
        channel_id=999120000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "retreat-char-b", TEST_GUILD_ID)

    # Create factions at war
    faction_a, faction_b = await create_faction_at_war(db_conn, "retreat-faction-a", "retreat-faction-b", "retreat-war")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create territories
    t1 = Territory(territory_id="RETREAT-T1", name="Combat Zone", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    t2 = Territory(territory_id="RETREAT-T2", name="Retreat Zone", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t2.upsert(db_conn)

    # Create adjacency
    adj = TerritoryAdjacency(territory_a_id="RETREAT-T1", territory_b_id="RETREAT-T2", guild_id=TEST_GUILD_ID)
    await adj.upsert(db_conn)

    # Create config
    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Create units - A is stronger
    unit_a = Unit(
        unit_id="retreat-unit-a", unit_type="infantry",
        owner_character_id=char_a.id, faction_id=faction_a.id,
        movement=2, organization=10, max_organization=10,
        attack=10, defense=5,  # Strong attacker
        current_territory_id="RETREAT-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_a.upsert(db_conn)

    unit_b = Unit(
        unit_id="retreat-unit-b", unit_type="infantry",
        owner_character_id=char_b.id, faction_id=faction_b.id,
        movement=2, organization=10, max_organization=10,
        attack=3, defense=3,  # Weaker
        current_territory_id="RETREAT-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_b.upsert(db_conn)

    # Execute combat phase
    events = await execute_combat_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify combat events generated
    event_types = [e.event_type for e in events]
    assert 'COMBAT_STARTED' in event_types
    assert 'COMBAT_ENDED' in event_types

    # Verify the weaker unit took org damage (10 attack > 3 defense)
    unit_b_updated = await Unit.fetch_by_unit_id(db_conn, "retreat-unit-b", TEST_GUILD_ID)
    assert unit_b_updated.organization < 10  # Took damage

    # The weaker side should have retreated
    assert 'COMBAT_RETREAT' in event_types or unit_b_updated.current_territory_id == "RETREAT-T2"


@pytest.mark.asyncio
async def test_org_damage_only_when_attack_exceeds_defense(db_conn, test_server):
    """Test that org damage only occurs when attack > defense."""
    # Setup
    char_a = Character(
        identifier="nodmg-char-a", name="Fighter A",
        channel_id=999130000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "nodmg-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="nodmg-char-b", name="Fighter B",
        channel_id=999130000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "nodmg-char-b", TEST_GUILD_ID)

    faction_a, faction_b = await create_faction_at_war(db_conn, "nodmg-faction-a", "nodmg-faction-b", "nodmg-war")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    t1 = Territory(territory_id="NODMG-T1", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    t2 = Territory(territory_id="NODMG-T2", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t2.upsert(db_conn)

    adj = TerritoryAdjacency(territory_a_id="NODMG-T1", territory_b_id="NODMG-T2", guild_id=TEST_GUILD_ID)
    await adj.upsert(db_conn)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Equal attack and defense - neither should take damage
    unit_a = Unit(
        unit_id="nodmg-unit-a", unit_type="infantry",
        owner_character_id=char_a.id, faction_id=faction_a.id,
        movement=2, organization=10, max_organization=10,
        attack=5, defense=5,
        current_territory_id="NODMG-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_a.upsert(db_conn)

    unit_b = Unit(
        unit_id="nodmg-unit-b", unit_type="infantry",
        owner_character_id=char_b.id, faction_id=faction_b.id,
        movement=2, organization=10, max_organization=10,
        attack=5, defense=5,
        current_territory_id="NODMG-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_b.upsert(db_conn)

    events = await execute_combat_phase(db_conn, TEST_GUILD_ID, 1)

    # Neither should have taken org damage (5 attack is not > 5 defense)
    org_damage_events = [e for e in events if e.event_type == 'COMBAT_ORG_DAMAGE']
    assert len(org_damage_events) == 0

    # Verify both units still at full org
    unit_a_updated = await Unit.fetch_by_unit_id(db_conn, "nodmg-unit-a", TEST_GUILD_ID)
    unit_b_updated = await Unit.fetch_by_unit_id(db_conn, "nodmg-unit-b", TEST_GUILD_ID)
    assert unit_a_updated.organization == 10
    assert unit_b_updated.organization == 10


@pytest.mark.asyncio
async def test_unit_disbanded_when_org_zero(db_conn, test_server):
    """Test that units are disbanded when organization reaches 0."""
    char_a = Character(
        identifier="disband-char-a", name="Strong Fighter",
        channel_id=999140000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "disband-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="disband-char-b", name="Weak Fighter",
        channel_id=999140000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "disband-char-b", TEST_GUILD_ID)

    faction_a, faction_b = await create_faction_at_war(db_conn, "disband-faction-a", "disband-faction-b", "disband-war")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    t1 = Territory(territory_id="DISBAND-T1", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Strong unit vs very weak unit with low org
    unit_a = Unit(
        unit_id="disband-unit-a", unit_type="infantry",
        owner_character_id=char_a.id, faction_id=faction_a.id,
        movement=2, organization=10, max_organization=10,
        attack=20, defense=10,  # Very strong
        current_territory_id="DISBAND-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_a.upsert(db_conn)

    unit_b = Unit(
        unit_id="disband-unit-b", unit_type="infantry",
        owner_character_id=char_b.id, faction_id=faction_b.id,
        movement=2, organization=2, max_organization=10,  # Very low org
        attack=1, defense=1,  # Very weak
        current_territory_id="DISBAND-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_b.upsert(db_conn)

    events = await execute_combat_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify unit_b was disbanded
    disbanded_events = [e for e in events if e.event_type == 'COMBAT_UNIT_DISBANDED']
    assert len(disbanded_events) > 0

    unit_b_updated = await Unit.fetch_by_unit_id(db_conn, "disband-unit-b", TEST_GUILD_ID)
    assert unit_b_updated.status == 'DISBANDED'
    assert unit_b_updated.organization <= 0


@pytest.mark.asyncio
async def test_city_not_captured_in_combat(db_conn, test_server):
    """Test that city territories are NOT captured during combat phase."""
    char_a = Character(
        identifier="city-char-a", name="City Attacker",
        channel_id=999150000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "city-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="city-char-b", name="City Defender",
        channel_id=999150000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "city-char-b", TEST_GUILD_ID)

    faction_a, faction_b = await create_faction_at_war(db_conn, "city-faction-a", "city-faction-b", "city-war")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create CITY territory controlled by faction_b
    t1 = Territory(
        territory_id="CITY-T1", name="Important City", terrain_type="city",
        controller_faction_id=faction_b.id,
        guild_id=TEST_GUILD_ID
    )
    await t1.upsert(db_conn)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Strong unit with capture action
    unit_a = Unit(
        unit_id="city-unit-a", unit_type="infantry",
        owner_character_id=char_a.id, faction_id=faction_a.id,
        movement=2, organization=10, max_organization=10,
        attack=20, defense=10,
        current_territory_id="CITY-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_a.upsert(db_conn)

    # Create capture order for unit_a
    order = Order(
        order_id="city-capture-order",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit_a.id] if hasattr(unit_a, 'id') else [],
        character_id=char_a.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.SUCCESS.value,
        order_data={'action': 'capture', 'path': ['CITY-T1']},
        result_data={'final_territory': 'CITY-T1'},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Weak defending unit
    unit_b = Unit(
        unit_id="city-unit-b", unit_type="infantry",
        owner_character_id=char_b.id, faction_id=faction_b.id,
        movement=2, organization=2, max_organization=10,
        attack=1, defense=1,
        current_territory_id="CITY-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_b.upsert(db_conn)

    events = await execute_combat_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify city was NOT captured
    capture_events = [e for e in events if e.event_type == 'TERRITORY_CAPTURED']
    assert len(capture_events) == 0

    # Verify territory still controlled by faction_b
    t1_updated = await Territory.fetch_by_territory_id(db_conn, "CITY-T1", TEST_GUILD_ID)
    assert t1_updated.controller_faction_id == faction_b.id


@pytest.mark.asyncio
async def test_rural_territory_captured_with_building_damage(db_conn, test_server):
    """Test that rural territories are captured and buildings take damage."""
    char_a = Character(
        identifier="rural-char-a", name="Rural Attacker",
        channel_id=999160000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "rural-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="rural-char-b", name="Rural Defender",
        channel_id=999160000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "rural-char-b", TEST_GUILD_ID)

    faction_a, faction_b = await create_faction_at_war(db_conn, "rural-faction-a", "rural-faction-b", "rural-war")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create RURAL territory controlled by faction_b
    t1 = Territory(
        territory_id="RURAL-T1", name="Rural Region", terrain_type="plains",
        controller_faction_id=faction_b.id,
        guild_id=TEST_GUILD_ID
    )
    await t1.upsert(db_conn)

    # Create a building in the territory
    building = Building(
        building_id="rural-building", name="Farm", building_type="farm",
        territory_id="RURAL-T1", durability=5, status="ACTIVE",
        guild_id=TEST_GUILD_ID
    )
    await building.upsert(db_conn)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Fetch unit_a internal ID after creation
    unit_a = Unit(
        unit_id="rural-unit-a", unit_type="infantry",
        owner_character_id=char_a.id, faction_id=faction_a.id,
        movement=2, organization=10, max_organization=10,
        attack=20, defense=10,
        current_territory_id="RURAL-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_a.upsert(db_conn)
    unit_a = await Unit.fetch_by_unit_id(db_conn, "rural-unit-a", TEST_GUILD_ID)

    # Create capture order
    order = Order(
        order_id="rural-capture-order",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit_a.id],
        character_id=char_a.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.SUCCESS.value,
        order_data={'action': 'capture', 'path': ['RURAL-T1']},
        result_data={'final_territory': 'RURAL-T1'},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Weak defender that will be defeated
    unit_b = Unit(
        unit_id="rural-unit-b", unit_type="infantry",
        owner_character_id=char_b.id, faction_id=faction_b.id,
        movement=2, organization=2, max_organization=10,
        attack=1, defense=1,
        current_territory_id="RURAL-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_b.upsert(db_conn)

    events = await execute_combat_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify territory was captured
    capture_events = [e for e in events if e.event_type == 'TERRITORY_CAPTURED']
    assert len(capture_events) == 1

    # Verify building took damage
    building_damage_events = [e for e in events if e.event_type == 'BUILDING_COMBAT_DAMAGE']
    assert len(building_damage_events) == 1

    building_updated = await Building.fetch_by_building_id(db_conn, "rural-building", TEST_GUILD_ID)
    assert building_updated.durability == 4  # Was 5, now 4


@pytest.mark.asyncio
async def test_action_conflict_triggers_combat(db_conn, test_server):
    """Test that neutral factions with conflicting capture orders fight."""
    char_a = Character(
        identifier="conflict-char-a", name="Captor A",
        channel_id=999170000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "conflict-char-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="conflict-char-b", name="Captor B",
        channel_id=999170000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "conflict-char-b", TEST_GUILD_ID)

    # Create factions but NOT at war
    faction_a = Faction(faction_id="conflict-faction-a", name="Neutral Faction A", guild_id=TEST_GUILD_ID)
    await faction_a.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, "conflict-faction-a", TEST_GUILD_ID)

    faction_b = Faction(faction_id="conflict-faction-b", name="Neutral Faction B", guild_id=TEST_GUILD_ID)
    await faction_b.upsert(db_conn)
    faction_b = await Faction.fetch_by_faction_id(db_conn, "conflict-faction-b", TEST_GUILD_ID)

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    t1 = Territory(territory_id="CONFLICT-T1", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Both units with capture actions
    unit_a = Unit(
        unit_id="conflict-unit-a", unit_type="infantry",
        owner_character_id=char_a.id, faction_id=faction_a.id,
        movement=2, organization=10, max_organization=10,
        attack=5, defense=5,
        current_territory_id="CONFLICT-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_a.upsert(db_conn)
    unit_a = await Unit.fetch_by_unit_id(db_conn, "conflict-unit-a", TEST_GUILD_ID)

    unit_b = Unit(
        unit_id="conflict-unit-b", unit_type="infantry",
        owner_character_id=char_b.id, faction_id=faction_b.id,
        movement=2, organization=10, max_organization=10,
        attack=5, defense=5,
        current_territory_id="CONFLICT-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_b.upsert(db_conn)
    unit_b = await Unit.fetch_by_unit_id(db_conn, "conflict-unit-b", TEST_GUILD_ID)

    # Create capture orders for both
    order_a = Order(
        order_id="conflict-order-a",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit_a.id],
        character_id=char_a.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.SUCCESS.value,
        order_data={'action': 'capture', 'path': ['CONFLICT-T1']},
        result_data={'final_territory': 'CONFLICT-T1'},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order_a.upsert(db_conn)

    order_b = Order(
        order_id="conflict-order-b",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit_b.id],
        character_id=char_b.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.SUCCESS.value,
        order_data={'action': 'capture', 'path': ['CONFLICT-T1']},
        result_data={'final_territory': 'CONFLICT-T1'},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order_b.upsert(db_conn)

    events = await execute_combat_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify combat occurred between neutral factions due to action conflict
    event_types = [e.event_type for e in events]
    assert 'COMBAT_STARTED' in event_types

    # Verify action conflict event was generated
    assert 'COMBAT_ACTION_CONFLICT' in event_types

    conflict_events = [e for e in events if e.event_type == 'COMBAT_ACTION_CONFLICT']
    assert len(conflict_events) >= 1
    assert 'recommendation' in conflict_events[0].event_data


@pytest.mark.asyncio
async def test_allied_factions_combine_stats(db_conn, test_server):
    """Test that allied factions combine their stats in combat."""
    # Create characters
    char_a = Character(identifier="allied-char-a", name="Ally A", channel_id=999180000000000001, guild_id=TEST_GUILD_ID)
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "allied-char-a", TEST_GUILD_ID)

    char_b = Character(identifier="allied-char-b", name="Ally B", channel_id=999180000000000002, guild_id=TEST_GUILD_ID)
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "allied-char-b", TEST_GUILD_ID)

    char_c = Character(identifier="allied-char-c", name="Enemy C", channel_id=999180000000000003, guild_id=TEST_GUILD_ID)
    await char_c.upsert(db_conn)
    char_c = await Character.fetch_by_identifier(db_conn, "allied-char-c", TEST_GUILD_ID)

    # Create factions
    faction_a = Faction(faction_id="allied-faction-a", name="Ally Faction A", guild_id=TEST_GUILD_ID)
    await faction_a.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, "allied-faction-a", TEST_GUILD_ID)

    faction_b = Faction(faction_id="allied-faction-b", name="Ally Faction B", guild_id=TEST_GUILD_ID)
    await faction_b.upsert(db_conn)
    faction_b = await Faction.fetch_by_faction_id(db_conn, "allied-faction-b", TEST_GUILD_ID)

    faction_c = Faction(faction_id="allied-faction-c", name="Enemy Faction C", guild_id=TEST_GUILD_ID)
    await faction_c.upsert(db_conn)
    faction_c = await Faction.fetch_by_faction_id(db_conn, "allied-faction-c", TEST_GUILD_ID)

    # Create alliance between A and B
    alliance = Alliance(
        faction_a_id=faction_a.id, faction_b_id=faction_b.id,
        status="ACTIVE", guild_id=TEST_GUILD_ID
    )
    await alliance.upsert(db_conn)

    # Put A and B at war with C
    war = War(war_id="allied-war", objective="Alliance War", guild_id=TEST_GUILD_ID)
    await war.upsert(db_conn)
    war = await War.fetch_by_id(db_conn, "allied-war", TEST_GUILD_ID)

    part_a = WarParticipant(war_id=war.id, faction_id=faction_a.id, side="SIDE_A", guild_id=TEST_GUILD_ID)
    await part_a.upsert(db_conn)
    part_b = WarParticipant(war_id=war.id, faction_id=faction_b.id, side="SIDE_A", guild_id=TEST_GUILD_ID)
    await part_b.upsert(db_conn)
    part_c = WarParticipant(war_id=war.id, faction_id=faction_c.id, side="SIDE_B", guild_id=TEST_GUILD_ID)
    await part_c.upsert(db_conn)

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)
    char_c.represented_faction_id = faction_c.id
    await char_c.upsert(db_conn)

    t1 = Territory(territory_id="ALLIED-T1", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    t2 = Territory(territory_id="ALLIED-T2", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t2.upsert(db_conn)
    adj = TerritoryAdjacency(territory_a_id="ALLIED-T1", territory_b_id="ALLIED-T2", guild_id=TEST_GUILD_ID)
    await adj.upsert(db_conn)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Ally A unit: attack 3, defense 3
    unit_a = Unit(
        unit_id="allied-unit-a", unit_type="infantry",
        owner_character_id=char_a.id, faction_id=faction_a.id,
        movement=2, organization=10, max_organization=10,
        attack=3, defense=3,
        current_territory_id="ALLIED-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_a.upsert(db_conn)

    # Ally B unit: attack 4, defense 4
    unit_b = Unit(
        unit_id="allied-unit-b", unit_type="infantry",
        owner_character_id=char_b.id, faction_id=faction_b.id,
        movement=2, organization=10, max_organization=10,
        attack=4, defense=4,
        current_territory_id="ALLIED-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_b.upsert(db_conn)

    # Enemy C unit: attack 5, defense 5 (weaker than combined allies 7/7)
    unit_c = Unit(
        unit_id="allied-unit-c", unit_type="infantry",
        owner_character_id=char_c.id, faction_id=faction_c.id,
        movement=2, organization=10, max_organization=10,
        attack=5, defense=5,
        current_territory_id="ALLIED-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_c.upsert(db_conn)

    events = await execute_combat_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify combat occurred
    event_types = [e.event_type for e in events]
    assert 'COMBAT_STARTED' in event_types

    # The enemy should take damage (combined ally attack 7 > enemy defense 5)
    unit_c_updated = await Unit.fetch_by_unit_id(db_conn, "allied-unit-c", TEST_GUILD_ID)
    assert unit_c_updated.organization < 10

    # Allied units should NOT take damage (enemy attack 5 <= ally combined defense 7)
    unit_a_updated = await Unit.fetch_by_unit_id(db_conn, "allied-unit-a", TEST_GUILD_ID)
    unit_b_updated = await Unit.fetch_by_unit_id(db_conn, "allied-unit-b", TEST_GUILD_ID)
    assert unit_a_updated.organization == 10
    assert unit_b_updated.organization == 10


# ============================================================================
# Infiltrator and Aerial Combat Exemption Tests
# ============================================================================

@pytest.mark.asyncio
async def test_infiltrator_excluded_from_combat(db_conn, test_server):
    """Test that infiltrator units in territory with hostiles don't trigger combat."""
    # Create characters
    char_a = Character(
        identifier="infil-combat-a", name="Infiltrator",
        channel_id=999300000000000001, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "infil-combat-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="infil-combat-b", name="Defender",
        channel_id=999300000000000002, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "infil-combat-b", TEST_GUILD_ID)

    # Create factions at war
    faction_a, faction_b = await create_faction_at_war(db_conn, "infil-combat-fa", "infil-combat-fb", "INFIL-COMBAT-WAR")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create territory
    t1 = Territory(territory_id="INFIL-COMBAT-T1", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Create infiltrator unit
    infiltrator = Unit(
        unit_id="infil-combat-unit", unit_type="spy",
        owner_character_id=char_a.id, faction_id=faction_a.id,
        movement=2, organization=10, max_organization=10,
        attack=1, defense=1,
        current_territory_id="INFIL-COMBAT-T1", is_naval=False,
        keywords=['infiltrator'],
        guild_id=TEST_GUILD_ID
    )
    await infiltrator.upsert(db_conn)

    # Create enemy unit
    enemy = Unit(
        unit_id="infil-combat-enemy", unit_type="infantry",
        owner_character_id=char_b.id, faction_id=faction_b.id,
        movement=2, organization=10, max_organization=10,
        attack=5, defense=5,
        current_territory_id="INFIL-COMBAT-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await enemy.upsert(db_conn)

    # Execute combat phase
    events = await execute_combat_phase(db_conn, TEST_GUILD_ID, 1)

    # No combat should occur (infiltrator is exempt, only 1 combatant unit remains)
    combat_started = [e for e in events if e.event_type == 'COMBAT_STARTED']
    assert len(combat_started) == 0

    # Both units should be unharmed
    infiltrator_updated = await Unit.fetch_by_unit_id(db_conn, "infil-combat-unit", TEST_GUILD_ID)
    enemy_updated = await Unit.fetch_by_unit_id(db_conn, "infil-combat-enemy", TEST_GUILD_ID)
    assert infiltrator_updated.organization == 10
    assert enemy_updated.organization == 10


@pytest.mark.asyncio
async def test_aerial_excluded_from_combat(db_conn, test_server):
    """Test that aerial units in territory with hostiles don't trigger combat."""
    # Create characters
    char_a = Character(
        identifier="aerial-combat-a", name="Aerial",
        channel_id=999300000000000003, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "aerial-combat-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="aerial-combat-b", name="Defender",
        channel_id=999300000000000004, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "aerial-combat-b", TEST_GUILD_ID)

    # Create factions at war
    faction_a, faction_b = await create_faction_at_war(db_conn, "aerial-combat-fa", "aerial-combat-fb", "AERIAL-COMBAT-WAR")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create territory
    t1 = Territory(territory_id="AERIAL-COMBAT-T1", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Create aerial unit
    aerial = Unit(
        unit_id="aerial-combat-unit", unit_type="flying_bison",
        owner_character_id=char_a.id, faction_id=faction_a.id,
        movement=3, organization=10, max_organization=10,
        attack=2, defense=2,
        current_territory_id="AERIAL-COMBAT-T1", is_naval=False,
        keywords=['aerial'],
        guild_id=TEST_GUILD_ID
    )
    await aerial.upsert(db_conn)

    # Create enemy unit
    enemy = Unit(
        unit_id="aerial-combat-enemy", unit_type="infantry",
        owner_character_id=char_b.id, faction_id=faction_b.id,
        movement=2, organization=10, max_organization=10,
        attack=5, defense=5,
        current_territory_id="AERIAL-COMBAT-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await enemy.upsert(db_conn)

    # Execute combat phase
    events = await execute_combat_phase(db_conn, TEST_GUILD_ID, 1)

    # No combat should occur (aerial is exempt, only 1 combatant unit remains)
    combat_started = [e for e in events if e.event_type == 'COMBAT_STARTED']
    assert len(combat_started) == 0

    # Both units should be unharmed
    aerial_updated = await Unit.fetch_by_unit_id(db_conn, "aerial-combat-unit", TEST_GUILD_ID)
    enemy_updated = await Unit.fetch_by_unit_id(db_conn, "aerial-combat-enemy", TEST_GUILD_ID)
    assert aerial_updated.organization == 10
    assert enemy_updated.organization == 10


@pytest.mark.asyncio
async def test_combat_still_occurs_with_non_exempt_units(db_conn, test_server):
    """Test that combat occurs when non-exempt units are present even if exempt units exist."""
    # Create characters
    char_a = Character(
        identifier="mixed-combat-a", name="Mixed A",
        channel_id=999300000000000005, guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "mixed-combat-a", TEST_GUILD_ID)

    char_b = Character(
        identifier="mixed-combat-b", name="Mixed B",
        channel_id=999300000000000006, guild_id=TEST_GUILD_ID
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "mixed-combat-b", TEST_GUILD_ID)

    # Create factions at war
    faction_a, faction_b = await create_faction_at_war(db_conn, "mixed-combat-fa", "mixed-combat-fb", "MIXED-COMBAT-WAR")

    char_a.represented_faction_id = faction_a.id
    await char_a.upsert(db_conn)
    char_b.represented_faction_id = faction_b.id
    await char_b.upsert(db_conn)

    # Create territory
    t1 = Territory(territory_id="MIXED-COMBAT-T1", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    t2 = Territory(territory_id="MIXED-COMBAT-T2", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t2.upsert(db_conn)
    adj = TerritoryAdjacency(territory_a_id="MIXED-COMBAT-T1", territory_b_id="MIXED-COMBAT-T2", guild_id=TEST_GUILD_ID)
    await adj.upsert(db_conn)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Create an infiltrator unit (exempt from combat)
    infiltrator = Unit(
        unit_id="mixed-infil", unit_type="spy",
        owner_character_id=char_a.id, faction_id=faction_a.id,
        movement=2, organization=10, max_organization=10,
        attack=1, defense=1,
        current_territory_id="MIXED-COMBAT-T1", is_naval=False,
        keywords=['infiltrator'],
        guild_id=TEST_GUILD_ID
    )
    await infiltrator.upsert(db_conn)

    # Create a regular combat unit from faction A
    unit_a = Unit(
        unit_id="mixed-unit-a", unit_type="infantry",
        owner_character_id=char_a.id, faction_id=faction_a.id,
        movement=2, organization=10, max_organization=10,
        attack=5, defense=3,
        current_territory_id="MIXED-COMBAT-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_a.upsert(db_conn)

    # Create enemy unit
    unit_b = Unit(
        unit_id="mixed-unit-b", unit_type="infantry",
        owner_character_id=char_b.id, faction_id=faction_b.id,
        movement=2, organization=10, max_organization=10,
        attack=4, defense=4,
        current_territory_id="MIXED-COMBAT-T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit_b.upsert(db_conn)

    # Execute combat phase
    events = await execute_combat_phase(db_conn, TEST_GUILD_ID, 1)

    # Combat SHOULD occur between the non-exempt units
    combat_started = [e for e in events if e.event_type == 'COMBAT_STARTED']
    assert len(combat_started) == 1

    # The infiltrator should NOT be involved - check participating_units
    combat_data = combat_started[0].event_data
    assert 'mixed-infil' not in combat_data['participating_units']
    assert 'mixed-unit-a' in combat_data['participating_units']
    assert 'mixed-unit-b' in combat_data['participating_units']

    # Infiltrator should be unharmed
    infiltrator_updated = await Unit.fetch_by_unit_id(db_conn, "mixed-infil", TEST_GUILD_ID)
    assert infiltrator_updated.organization == 10
