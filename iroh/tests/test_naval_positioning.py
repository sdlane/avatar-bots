"""
Tests for the naval unit positioning system.

Naval units can occupy multiple territories simultaneously. This module tests:
- Database model for NavalUnitPosition
- Naval movement handlers for convoy, patrol, transit, transport
- Order validation for naval orders
- Integration with existing transport system
"""
import pytest
from datetime import datetime

from db import (
    Unit, UnitType, Territory, Character, Order, WargameConfig,
    TerritoryAdjacency, NavalUnitPosition, Faction, FactionMember
)
from order_types import OrderType, OrderStatus, TurnPhase
from handlers.naval_movement_handlers import (
    calculate_naval_window_size,
    calculate_occupied_territories,
    validate_path_water_only,
    validate_naval_order_overlap,
    validate_transport_coastal,
    validate_territory_count,
    validate_naval_order,
    process_naval_convoy,
    process_naval_patrol,
    process_naval_transit,
    process_naval_transport,
    execute_naval_movement_phase,
    get_naval_units_in_territory,
    initialize_naval_position_from_current,
)

# Test guild ID - must match conftest.py
TEST_GUILD_ID = 999999999999999999


# ============================================================================
# Database Model Tests
# ============================================================================

@pytest.mark.asyncio
async def test_naval_unit_position_upsert(db_conn, test_server):
    """Test creating and updating naval unit positions."""
    # Create a naval unit
    unit_type = UnitType(
        type_id='test-fleet', name='Test Fleet',
        is_naval=True, movement=3,
        guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    char = Character(
        identifier='test-char', name='Test Character',
        user_id=12345, channel_id=999000000000000001, guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    unit = Unit(
        unit_id='fleet-1', name='Fleet One',
        unit_type='test-fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    # Create position
    position = NavalUnitPosition(
        unit_id=unit.id,
        territory_id='ocean-1',
        position_index=0,
        guild_id=TEST_GUILD_ID
    )
    await position.upsert(db_conn)
    assert position.id is not None

    # Update position
    position.position_index = 1
    await position.upsert(db_conn)

    # Verify update
    positions = await NavalUnitPosition.fetch_by_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert len(positions) == 1
    assert positions[0].position_index == 1


@pytest.mark.asyncio
async def test_naval_unit_position_delete_for_unit(db_conn, test_server):
    """Test deleting all positions for a naval unit."""
    # Create unit with multiple positions
    unit_type = UnitType(
        type_id='test-fleet', name='Test Fleet',
        is_naval=True, movement=3,
        guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    char = Character(
        identifier='test-char', name='Test Character',
        user_id=12345, channel_id=999000000000000001, guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    unit = Unit(
        unit_id='fleet-1', name='Fleet One',
        unit_type='test-fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    # Create multiple positions
    await NavalUnitPosition.set_positions(db_conn, unit.id, ['ocean-1', 'ocean-2', 'ocean-3'], TEST_GUILD_ID)

    # Verify positions exist
    positions = await NavalUnitPosition.fetch_by_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert len(positions) == 3

    # Delete all positions
    deleted = await NavalUnitPosition.delete_for_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert deleted == 3

    # Verify deletion
    positions = await NavalUnitPosition.fetch_by_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert len(positions) == 0


@pytest.mark.asyncio
async def test_naval_unit_position_fetch_by_unit_ordered(db_conn, test_server):
    """Test fetching positions returns them in order by position_index."""
    # Create unit
    unit_type = UnitType(
        type_id='test-fleet', name='Test Fleet',
        is_naval=True, movement=3,
        guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    char = Character(
        identifier='test-char', name='Test Character',
        user_id=12345, channel_id=999000000000000001, guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    unit = Unit(
        unit_id='fleet-1', name='Fleet One',
        unit_type='test-fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    # Create positions in reverse order
    for i, territory in enumerate(['ocean-3', 'ocean-1', 'ocean-2']):
        position = NavalUnitPosition(
            unit_id=unit.id,
            territory_id=territory,
            position_index=i,
            guild_id=TEST_GUILD_ID
        )
        await position.upsert(db_conn)

    # Fetch and verify order
    positions = await NavalUnitPosition.fetch_by_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert len(positions) == 3
    assert positions[0].territory_id == 'ocean-3'
    assert positions[0].position_index == 0
    assert positions[1].territory_id == 'ocean-1'
    assert positions[1].position_index == 1
    assert positions[2].territory_id == 'ocean-2'
    assert positions[2].position_index == 2


@pytest.mark.asyncio
async def test_naval_unit_position_fetch_units_in_territory(db_conn, test_server):
    """Test fetching all naval units occupying a territory."""
    # Create two naval units
    unit_type = UnitType(
        type_id='test-fleet', name='Test Fleet',
        is_naval=True, movement=3,
        guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    char = Character(
        identifier='test-char', name='Test Character',
        user_id=12345, channel_id=999000000000000001, guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    unit1 = Unit(
        unit_id='fleet-1', name='Fleet One',
        unit_type='test-fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3,
        guild_id=TEST_GUILD_ID
    )
    await unit1.upsert(db_conn)
    unit1 = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    unit2 = Unit(
        unit_id='fleet-2', name='Fleet Two',
        unit_type='test-fleet', owner_character_id=char.id,
        current_territory_id='ocean-2', is_naval=True, movement=3,
        guild_id=TEST_GUILD_ID
    )
    await unit2.upsert(db_conn)
    unit2 = await Unit.fetch_by_unit_id(db_conn, 'fleet-2', TEST_GUILD_ID)

    # Both units occupy ocean-1, only unit2 occupies ocean-2
    await NavalUnitPosition.set_positions(db_conn, unit1.id, ['ocean-1'], TEST_GUILD_ID)
    await NavalUnitPosition.set_positions(db_conn, unit2.id, ['ocean-1', 'ocean-2'], TEST_GUILD_ID)

    # Check ocean-1 (both units)
    units_in_1 = await NavalUnitPosition.fetch_units_in_territory(db_conn, 'ocean-1', TEST_GUILD_ID)
    assert len(units_in_1) == 2
    assert set(units_in_1) == {unit1.id, unit2.id}

    # Check ocean-2 (only unit2)
    units_in_2 = await NavalUnitPosition.fetch_units_in_territory(db_conn, 'ocean-2', TEST_GUILD_ID)
    assert len(units_in_2) == 1
    assert units_in_2[0] == unit2.id


@pytest.mark.asyncio
async def test_naval_unit_position_set_positions_atomic(db_conn, test_server):
    """Test that set_positions atomically replaces all positions."""
    # Create unit
    unit_type = UnitType(
        type_id='test-fleet', name='Test Fleet',
        is_naval=True, movement=3,
        guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    char = Character(
        identifier='test-char', name='Test Character',
        user_id=12345, channel_id=999000000000000001, guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    unit = Unit(
        unit_id='fleet-1', name='Fleet One',
        unit_type='test-fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    # Set initial positions
    await NavalUnitPosition.set_positions(db_conn, unit.id, ['ocean-1', 'ocean-2'], TEST_GUILD_ID)
    positions = await NavalUnitPosition.fetch_territories_by_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert positions == ['ocean-1', 'ocean-2']

    # Replace with new positions
    await NavalUnitPosition.set_positions(db_conn, unit.id, ['ocean-3', 'ocean-4', 'ocean-5'], TEST_GUILD_ID)
    positions = await NavalUnitPosition.fetch_territories_by_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert positions == ['ocean-3', 'ocean-4', 'ocean-5']


# ============================================================================
# Helper Function Tests
# ============================================================================

def test_calculate_naval_window_size_convoy():
    """Test window size calculation for convoy action."""
    from db import Unit
    units = [
        Unit(unit_id='u1', movement=3, guild_id=TEST_GUILD_ID),
        Unit(unit_id='u2', movement=5, guild_id=TEST_GUILD_ID),
    ]
    # Convoy uses slowest unit's movement, no bonus
    assert calculate_naval_window_size(units, 'naval_convoy') == 3


def test_calculate_naval_window_size_transit():
    """Test window size calculation for transit action."""
    from db import Unit
    units = [
        Unit(unit_id='u1', movement=3, guild_id=TEST_GUILD_ID),
        Unit(unit_id='u2', movement=5, guild_id=TEST_GUILD_ID),
    ]
    # Transit uses slowest unit's movement + 1
    assert calculate_naval_window_size(units, 'naval_transit') == 4


def test_calculate_naval_window_size_transport():
    """Test window size calculation for transport action."""
    from db import Unit
    units = [
        Unit(unit_id='u1', movement=3, guild_id=TEST_GUILD_ID),
    ]
    # Transport uses slowest unit's movement, no bonus
    assert calculate_naval_window_size(units, 'naval_transport') == 3


def test_calculate_occupied_territories_convoy():
    """Test occupied territories for convoy action."""
    path = ['ocean-1', 'ocean-2', 'ocean-3', 'ocean-4', 'ocean-5']

    # Convoy occupies all territories up to window size
    occupied = calculate_occupied_territories('naval_convoy', path, window_size=3, window_start_index=0)
    assert occupied == ['ocean-1', 'ocean-2', 'ocean-3']


def test_calculate_occupied_territories_transit_start():
    """Test occupied territories for transit at start."""
    path = ['ocean-1', 'ocean-2', 'ocean-3', 'ocean-4', 'ocean-5']

    # Transit window at start
    occupied = calculate_occupied_territories('naval_transit', path, window_size=3, window_start_index=0)
    assert occupied == ['ocean-1', 'ocean-2', 'ocean-3']


def test_calculate_occupied_territories_transit_mid():
    """Test occupied territories for transit midway."""
    path = ['ocean-1', 'ocean-2', 'ocean-3', 'ocean-4', 'ocean-5']

    # Transit window advanced
    occupied = calculate_occupied_territories('naval_transit', path, window_size=3, window_start_index=2)
    assert occupied == ['ocean-3', 'ocean-4', 'ocean-5']


def test_calculate_occupied_territories_transit_end():
    """Test occupied territories for transit at end (only final territory)."""
    path = ['ocean-1', 'ocean-2', 'ocean-3', 'ocean-4', 'ocean-5']

    # Transit window past end
    occupied = calculate_occupied_territories('naval_transit', path, window_size=3, window_start_index=5)
    assert occupied == ['ocean-5']  # Only final territory


def test_calculate_occupied_territories_transport_waiting():
    """Test occupied territories for transport while waiting."""
    path = ['ocean-1', 'ocean-2', 'ocean-3', 'ocean-4']

    # Transport waiting - only first territory
    occupied = calculate_occupied_territories('naval_transport', path, window_size=3, window_start_index=0, waiting_for_cargo=True)
    assert occupied == ['ocean-1']


def test_calculate_occupied_territories_transport_moving():
    """Test occupied territories for transport after cargo boarded."""
    path = ['ocean-1', 'ocean-2', 'ocean-3', 'ocean-4']

    # Transport moving - sliding window
    occupied = calculate_occupied_territories('naval_transport', path, window_size=3, window_start_index=0, waiting_for_cargo=False)
    assert occupied == ['ocean-1', 'ocean-2', 'ocean-3']


# ============================================================================
# Validation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_validate_path_water_only_valid(db_conn, test_server):
    """Test validation passes for all-water path."""
    # Create water territories
    for i in range(3):
        territory = Territory(
            territory_id=f'ocean-{i+1}',
            terrain_type='ocean',
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)

    valid, error = await validate_path_water_only(db_conn, ['ocean-1', 'ocean-2', 'ocean-3'], TEST_GUILD_ID)
    assert valid is True
    assert error == ""


@pytest.mark.asyncio
async def test_validate_path_water_only_invalid(db_conn, test_server):
    """Test validation fails when path contains land."""
    # Create mixed territories
    ocean = Territory(territory_id='ocean-1', terrain_type='ocean', guild_id=TEST_GUILD_ID)
    await ocean.upsert(db_conn)
    land = Territory(territory_id='plains-1', terrain_type='plains', guild_id=TEST_GUILD_ID)
    await land.upsert(db_conn)

    valid, error = await validate_path_water_only(db_conn, ['ocean-1', 'plains-1'], TEST_GUILD_ID)
    assert valid is False
    assert 'plains-1' in error


@pytest.mark.asyncio
async def test_validate_naval_order_overlap_first_order(db_conn, test_server):
    """Test first order must include initial territory."""
    # Create unit at ocean-1
    unit_type = UnitType(type_id='test-fleet', name='Test Fleet', is_naval=True, movement=3, guild_id=TEST_GUILD_ID)
    await unit_type.upsert(db_conn)

    char = Character(identifier='test-char', name='Test', user_id=12345, channel_id=999000000000000001, guild_id=TEST_GUILD_ID)
    await char.upsert(db_conn)

    unit = Unit(
        unit_id='fleet-1', unit_type='test-fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3, guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    # Valid - includes initial territory
    valid, error = await validate_naval_order_overlap(db_conn, unit.id, ['ocean-1', 'ocean-2'], TEST_GUILD_ID)
    assert valid is True

    # Invalid - does not include initial territory
    valid, error = await validate_naval_order_overlap(db_conn, unit.id, ['ocean-2', 'ocean-3'], TEST_GUILD_ID)
    assert valid is False
    assert 'ocean-1' in error


@pytest.mark.asyncio
async def test_validate_naval_order_overlap_subsequent(db_conn, test_server):
    """Test subsequent orders must overlap with current positions."""
    # Create unit with existing positions
    unit_type = UnitType(type_id='test-fleet', name='Test Fleet', is_naval=True, movement=3, guild_id=TEST_GUILD_ID)
    await unit_type.upsert(db_conn)

    char = Character(identifier='test-char', name='Test', user_id=12345, channel_id=999000000000000001, guild_id=TEST_GUILD_ID)
    await char.upsert(db_conn)

    unit = Unit(
        unit_id='fleet-1', unit_type='test-fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3, guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    # Set current positions
    await NavalUnitPosition.set_positions(db_conn, unit.id, ['ocean-1', 'ocean-2', 'ocean-3'], TEST_GUILD_ID)

    # Valid - overlaps with current
    valid, error = await validate_naval_order_overlap(db_conn, unit.id, ['ocean-3', 'ocean-4', 'ocean-5'], TEST_GUILD_ID)
    assert valid is True

    # Invalid - no overlap
    valid, error = await validate_naval_order_overlap(db_conn, unit.id, ['ocean-5', 'ocean-6', 'ocean-7'], TEST_GUILD_ID)
    assert valid is False


@pytest.mark.asyncio
async def test_validate_transport_coastal_valid(db_conn, test_server):
    """Test transport validation passes when first territory is adjacent to land."""
    # Create territories
    ocean = Territory(territory_id='ocean-1', terrain_type='ocean', guild_id=TEST_GUILD_ID)
    await ocean.upsert(db_conn)
    coast = Territory(territory_id='coast-1', terrain_type='plains', guild_id=TEST_GUILD_ID)
    await coast.upsert(db_conn)

    # Create adjacency
    adj = TerritoryAdjacency(territory_a_id='coast-1', territory_b_id='ocean-1', guild_id=TEST_GUILD_ID)
    await adj.upsert(db_conn)

    valid, error = await validate_transport_coastal(db_conn, 'ocean-1', TEST_GUILD_ID)
    assert valid is True


@pytest.mark.asyncio
async def test_validate_transport_coastal_invalid(db_conn, test_server):
    """Test transport validation fails when first territory has no adjacent land."""
    # Create only water territories
    ocean1 = Territory(territory_id='ocean-1', terrain_type='ocean', guild_id=TEST_GUILD_ID)
    await ocean1.upsert(db_conn)
    ocean2 = Territory(territory_id='ocean-2', terrain_type='ocean', guild_id=TEST_GUILD_ID)
    await ocean2.upsert(db_conn)

    # Create adjacency (water to water only)
    adj = TerritoryAdjacency(territory_a_id='ocean-1', territory_b_id='ocean-2', guild_id=TEST_GUILD_ID)
    await adj.upsert(db_conn)

    valid, error = await validate_transport_coastal(db_conn, 'ocean-1', TEST_GUILD_ID)
    assert valid is False
    assert 'adjacent to at least one land' in error


def test_validate_territory_count_convoy():
    """Test territory count validation for convoy (must fit in movement stat)."""
    # Valid - within limit
    valid, error = validate_territory_count(['o1', 'o2', 'o3'], max_territories=3, action='naval_convoy')
    assert valid is True

    # Invalid - exceeds limit
    valid, error = validate_territory_count(['o1', 'o2', 'o3', 'o4', 'o5'], max_territories=3, action='naval_convoy')
    assert valid is False


def test_validate_territory_count_transit():
    """Test territory count validation for transit (can be longer since it's a path)."""
    # Transit can have longer path since it uses sliding window
    valid, error = validate_territory_count(['o1', 'o2', 'o3', 'o4', 'o5', 'o6', 'o7', 'o8', 'o9', 'o10'],
                                            max_territories=3, action='naval_transit')
    assert valid is True


# ============================================================================
# Convoy Tests
# ============================================================================

@pytest.mark.asyncio
async def test_convoy_occupies_all_territories(db_conn, test_server):
    """Test convoy action occupies all specified territories."""
    # Setup
    for i in range(3):
        t = Territory(territory_id=f'ocean-{i+1}', terrain_type='ocean', guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    unit_type = UnitType(type_id='fleet', is_naval=True, movement=3, guild_id=TEST_GUILD_ID)
    await unit_type.upsert(db_conn)

    char = Character(identifier='c1', name='Captain', user_id=1, channel_id=999000000000000001, guild_id=TEST_GUILD_ID)
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, 'c1', TEST_GUILD_ID)

    unit = Unit(
        unit_id='fleet-1', unit_type='fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3, guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    # Initialize position
    await NavalUnitPosition.set_positions(db_conn, unit.id, ['ocean-1'], TEST_GUILD_ID)

    order = Order(
        order_id='order-1',
        order_type=OrderType.UNIT.value,
        character_id=char.id,
        unit_ids=[unit.id],
        status=OrderStatus.PENDING.value,
        phase=TurnPhase.MOVEMENT.value,
        order_data={'action': 'naval_convoy', 'path': ['ocean-1', 'ocean-2', 'ocean-3']},
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Process
    updated_order, events = await process_naval_convoy(db_conn, order, [unit], TEST_GUILD_ID, 1)

    # Verify
    assert updated_order.status == OrderStatus.SUCCESS.value
    positions = await NavalUnitPosition.fetch_territories_by_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert positions == ['ocean-1', 'ocean-2', 'ocean-3']
    assert len(events) == 1
    assert events[0].event_type == 'NAVAL_POSITION_SET'


# ============================================================================
# Patrol Tests
# ============================================================================

@pytest.mark.asyncio
async def test_patrol_occupies_all_territories(db_conn, test_server):
    """Test patrol action occupies all specified territories."""
    # Setup
    for i in range(3):
        t = Territory(territory_id=f'ocean-{i+1}', terrain_type='ocean', guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    unit_type = UnitType(type_id='fleet', is_naval=True, movement=3, guild_id=TEST_GUILD_ID)
    await unit_type.upsert(db_conn)

    char = Character(identifier='c1', name='Captain', user_id=1, channel_id=999000000000000001, guild_id=TEST_GUILD_ID)
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, 'c1', TEST_GUILD_ID)

    unit = Unit(
        unit_id='fleet-1', unit_type='fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3, guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    await NavalUnitPosition.set_positions(db_conn, unit.id, ['ocean-1'], TEST_GUILD_ID)

    order = Order(
        order_id='order-1',
        order_type=OrderType.UNIT.value,
        character_id=char.id,
        unit_ids=[unit.id],
        status=OrderStatus.PENDING.value,
        phase=TurnPhase.MOVEMENT.value,
        order_data={'action': 'naval_patrol', 'path': ['ocean-1', 'ocean-2', 'ocean-3']},
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Process
    updated_order, events = await process_naval_patrol(db_conn, order, [unit], TEST_GUILD_ID, 1)

    # Verify
    assert updated_order.status == OrderStatus.SUCCESS.value
    positions = await NavalUnitPosition.fetch_territories_by_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert positions == ['ocean-1', 'ocean-2', 'ocean-3']


# ============================================================================
# Transit Tests
# ============================================================================

@pytest.mark.asyncio
async def test_transit_first_turn_window(db_conn, test_server):
    """Test transit occupies first (movement + 1) territories on first turn."""
    # Setup - 6 ocean territories
    for i in range(6):
        t = Territory(territory_id=f'ocean-{i+1}', terrain_type='ocean', guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    unit_type = UnitType(type_id='fleet', is_naval=True, movement=2, guild_id=TEST_GUILD_ID)
    await unit_type.upsert(db_conn)

    char = Character(identifier='c1', name='Captain', user_id=1, channel_id=999000000000000001, guild_id=TEST_GUILD_ID)
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, 'c1', TEST_GUILD_ID)

    unit = Unit(
        unit_id='fleet-1', unit_type='fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=2, guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    await NavalUnitPosition.set_positions(db_conn, unit.id, ['ocean-1'], TEST_GUILD_ID)

    order = Order(
        order_id='order-1',
        order_type=OrderType.UNIT.value,
        character_id=char.id,
        unit_ids=[unit.id],
        status=OrderStatus.PENDING.value,
        phase=TurnPhase.MOVEMENT.value,
        order_data={'action': 'naval_transit', 'path': ['ocean-1', 'ocean-2', 'ocean-3', 'ocean-4', 'ocean-5', 'ocean-6']},
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Process first turn
    updated_order, events = await process_naval_transit(db_conn, order, [unit], TEST_GUILD_ID, 1)

    # Verify - window size is movement + 1 = 3
    assert updated_order.status == OrderStatus.ONGOING.value
    positions = await NavalUnitPosition.fetch_territories_by_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert positions == ['ocean-1', 'ocean-2', 'ocean-3']
    assert updated_order.result_data['window_start_index'] == 0


@pytest.mark.asyncio
async def test_transit_window_advances(db_conn, test_server):
    """Test transit window advances on subsequent turns."""
    # Setup
    for i in range(6):
        t = Territory(territory_id=f'ocean-{i+1}', terrain_type='ocean', guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    unit_type = UnitType(type_id='fleet', is_naval=True, movement=2, guild_id=TEST_GUILD_ID)
    await unit_type.upsert(db_conn)

    char = Character(identifier='c1', name='Captain', user_id=1, channel_id=999000000000000001, guild_id=TEST_GUILD_ID)
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, 'c1', TEST_GUILD_ID)

    unit = Unit(
        unit_id='fleet-1', unit_type='fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=2, guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    await NavalUnitPosition.set_positions(db_conn, unit.id, ['ocean-1', 'ocean-2', 'ocean-3'], TEST_GUILD_ID)

    # Create order that's already ongoing with window_start_index=0
    order = Order(
        order_id='order-1',
        order_type=OrderType.UNIT.value,
        character_id=char.id,
        unit_ids=[unit.id],
        status=OrderStatus.ONGOING.value,
        phase=TurnPhase.MOVEMENT.value,
        order_data={'action': 'naval_transit', 'path': ['ocean-1', 'ocean-2', 'ocean-3', 'ocean-4', 'ocean-5', 'ocean-6']},
        result_data={'window_start_index': 0, 'occupied_territories': ['ocean-1', 'ocean-2', 'ocean-3']},
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Process (window should advance by window_size=3)
    updated_order, events = await process_naval_transit(db_conn, order, [unit], TEST_GUILD_ID, 2)

    # Verify window advanced
    positions = await NavalUnitPosition.fetch_territories_by_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert positions == ['ocean-4', 'ocean-5', 'ocean-6']
    assert updated_order.result_data['window_start_index'] == 3


@pytest.mark.asyncio
async def test_transit_end_of_path(db_conn, test_server):
    """Test transit at end of path only occupies final territory."""
    # Setup
    for i in range(4):
        t = Territory(territory_id=f'ocean-{i+1}', terrain_type='ocean', guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    unit_type = UnitType(type_id='fleet', is_naval=True, movement=2, guild_id=TEST_GUILD_ID)
    await unit_type.upsert(db_conn)

    char = Character(identifier='c1', name='Captain', user_id=1, channel_id=999000000000000001, guild_id=TEST_GUILD_ID)
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, 'c1', TEST_GUILD_ID)

    unit = Unit(
        unit_id='fleet-1', unit_type='fleet', owner_character_id=char.id,
        current_territory_id='ocean-3', is_naval=True, movement=2, guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    await NavalUnitPosition.set_positions(db_conn, unit.id, ['ocean-2', 'ocean-3', 'ocean-4'], TEST_GUILD_ID)

    # Create order near end of path
    order = Order(
        order_id='order-1',
        order_type=OrderType.UNIT.value,
        character_id=char.id,
        unit_ids=[unit.id],
        status=OrderStatus.ONGOING.value,
        phase=TurnPhase.MOVEMENT.value,
        order_data={'action': 'naval_transit', 'path': ['ocean-1', 'ocean-2', 'ocean-3', 'ocean-4']},
        result_data={'window_start_index': 1},
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Process (window advances past end)
    updated_order, events = await process_naval_transit(db_conn, order, [unit], TEST_GUILD_ID, 2)

    # Verify only final territory
    assert updated_order.status == OrderStatus.SUCCESS.value
    assert updated_order.result_data['path_complete'] is True
    positions = await NavalUnitPosition.fetch_territories_by_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert positions == ['ocean-4']


# ============================================================================
# Transport Tests
# ============================================================================

@pytest.mark.asyncio
async def test_transport_waits_at_first_territory(db_conn, test_server):
    """Test transport only occupies first territory while waiting for cargo."""
    # Setup
    for i in range(4):
        t = Territory(territory_id=f'ocean-{i+1}', terrain_type='ocean', guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    # Add adjacent land for coastal validation
    coast = Territory(territory_id='coast-1', terrain_type='plains', guild_id=TEST_GUILD_ID)
    await coast.upsert(db_conn)
    adj = TerritoryAdjacency(territory_a_id='coast-1', territory_b_id='ocean-1', guild_id=TEST_GUILD_ID)
    await adj.upsert(db_conn)

    unit_type = UnitType(type_id='fleet', is_naval=True, movement=3, guild_id=TEST_GUILD_ID)
    await unit_type.upsert(db_conn)

    char = Character(identifier='c1', name='Captain', user_id=1, channel_id=999000000000000001, guild_id=TEST_GUILD_ID)
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, 'c1', TEST_GUILD_ID)

    unit = Unit(
        unit_id='fleet-1', unit_type='fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3, guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    await NavalUnitPosition.set_positions(db_conn, unit.id, ['ocean-1'], TEST_GUILD_ID)

    order = Order(
        order_id='order-1',
        order_type=OrderType.UNIT.value,
        character_id=char.id,
        unit_ids=[unit.id],
        status=OrderStatus.PENDING.value,
        phase=TurnPhase.MOVEMENT.value,
        order_data={'action': 'naval_transport', 'path': ['ocean-1', 'ocean-2', 'ocean-3', 'ocean-4']},
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Process
    updated_order, events = await process_naval_transport(db_conn, order, [unit], TEST_GUILD_ID, 1)

    # Verify - waiting, only first territory
    assert updated_order.result_data['waiting_for_cargo'] is True
    positions = await NavalUnitPosition.fetch_territories_by_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert positions == ['ocean-1']
    assert events[0].event_type == 'NAVAL_WAITING'


@pytest.mark.asyncio
async def test_transport_window_after_boarding(db_conn, test_server):
    """Test transport occupies sliding window after cargo boards."""
    # Setup
    for i in range(5):
        t = Territory(territory_id=f'ocean-{i+1}', terrain_type='ocean', guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    unit_type = UnitType(type_id='fleet', is_naval=True, movement=3, guild_id=TEST_GUILD_ID)
    await unit_type.upsert(db_conn)

    char = Character(identifier='c1', name='Captain', user_id=1, channel_id=999000000000000001, guild_id=TEST_GUILD_ID)
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, 'c1', TEST_GUILD_ID)

    unit = Unit(
        unit_id='fleet-1', unit_type='fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3, guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    await NavalUnitPosition.set_positions(db_conn, unit.id, ['ocean-1'], TEST_GUILD_ID)

    # Create order where cargo has boarded
    order = Order(
        order_id='order-1',
        order_type=OrderType.UNIT.value,
        character_id=char.id,
        unit_ids=[unit.id],
        status=OrderStatus.ONGOING.value,
        phase=TurnPhase.MOVEMENT.value,
        order_data={'action': 'naval_transport', 'path': ['ocean-1', 'ocean-2', 'ocean-3', 'ocean-4', 'ocean-5']},
        result_data={'waiting_for_cargo': False, 'window_start_index': 0, 'carrying_units': [99]},
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Process
    updated_order, events = await process_naval_transport(db_conn, order, [unit], TEST_GUILD_ID, 2)

    # Verify - window advances (movement=3, so window is 3 territories)
    # window_start_index was 0, advances by window_size=3 to index 3
    # Path has 5 elements (indices 0-4), and 3+3=6 > 5, so path is complete
    # When path complete, only the final territory is occupied
    positions = await NavalUnitPosition.fetch_territories_by_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert positions == ['ocean-5']  # Path complete, only final territory


# ============================================================================
# Edge Case Tests
# ============================================================================

@pytest.mark.asyncio
async def test_no_orders_stays_at_initial(db_conn, test_server):
    """Test unit with no orders stays at initial territory."""
    t = Territory(territory_id='ocean-1', terrain_type='ocean', guild_id=TEST_GUILD_ID)
    await t.upsert(db_conn)

    unit_type = UnitType(type_id='fleet', is_naval=True, movement=3, guild_id=TEST_GUILD_ID)
    await unit_type.upsert(db_conn)

    char = Character(identifier='c1', name='Captain', user_id=1, channel_id=999000000000000001, guild_id=TEST_GUILD_ID)
    await char.upsert(db_conn)

    unit = Unit(
        unit_id='fleet-1', unit_type='fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3, guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    # Initialize from current
    await initialize_naval_position_from_current(db_conn, unit, TEST_GUILD_ID)

    positions = await NavalUnitPosition.fetch_territories_by_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert positions == ['ocean-1']


@pytest.mark.asyncio
async def test_get_naval_units_in_territory(db_conn, test_server):
    """Test getting all naval units in a territory."""
    t = Territory(territory_id='ocean-1', terrain_type='ocean', guild_id=TEST_GUILD_ID)
    await t.upsert(db_conn)

    unit_type = UnitType(type_id='fleet', is_naval=True, movement=3, guild_id=TEST_GUILD_ID)
    await unit_type.upsert(db_conn)

    char = Character(identifier='c1', name='Captain', user_id=1, channel_id=999000000000000001, guild_id=TEST_GUILD_ID)
    await char.upsert(db_conn)

    unit1 = Unit(
        unit_id='fleet-1', unit_type='fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3, status='ACTIVE', guild_id=TEST_GUILD_ID
    )
    await unit1.upsert(db_conn)
    unit1 = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    unit2 = Unit(
        unit_id='fleet-2', unit_type='fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3, status='ACTIVE', guild_id=TEST_GUILD_ID
    )
    await unit2.upsert(db_conn)
    unit2 = await Unit.fetch_by_unit_id(db_conn, 'fleet-2', TEST_GUILD_ID)

    await NavalUnitPosition.set_positions(db_conn, unit1.id, ['ocean-1'], TEST_GUILD_ID)
    await NavalUnitPosition.set_positions(db_conn, unit2.id, ['ocean-1'], TEST_GUILD_ID)

    units = await get_naval_units_in_territory(db_conn, 'ocean-1', TEST_GUILD_ID)
    assert len(units) == 2
    unit_ids = [u.unit_id for u in units]
    assert 'fleet-1' in unit_ids
    assert 'fleet-2' in unit_ids


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.asyncio
async def test_execute_naval_movement_phase(db_conn, test_server):
    """Test the full naval movement phase execution."""
    # Setup wargame config
    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Create territories
    for i in range(4):
        t = Territory(territory_id=f'ocean-{i+1}', terrain_type='ocean', guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    unit_type = UnitType(type_id='fleet', is_naval=True, movement=3, guild_id=TEST_GUILD_ID)
    await unit_type.upsert(db_conn)

    char = Character(identifier='c1', name='Captain', user_id=1, channel_id=999000000000000001, guild_id=TEST_GUILD_ID)
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, 'c1', TEST_GUILD_ID)

    unit = Unit(
        unit_id='fleet-1', unit_type='fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3, status='ACTIVE', guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    # Initialize starting position
    await NavalUnitPosition.set_positions(db_conn, unit.id, ['ocean-1'], TEST_GUILD_ID)

    # Create convoy order
    order = Order(
        order_id='order-1',
        order_type=OrderType.UNIT.value,
        character_id=char.id,
        unit_ids=[unit.id],
        status=OrderStatus.PENDING.value,
        phase=TurnPhase.MOVEMENT.value,
        order_data={'action': 'naval_convoy', 'path': ['ocean-1', 'ocean-2', 'ocean-3']},
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute phase
    events = await execute_naval_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify
    assert len(events) > 0
    updated_order = await Order.fetch_by_order_id(db_conn, 'order-1', TEST_GUILD_ID)
    assert updated_order.status == OrderStatus.SUCCESS.value

    positions = await NavalUnitPosition.fetch_territories_by_unit(db_conn, unit.id, TEST_GUILD_ID)
    assert positions == ['ocean-1', 'ocean-2', 'ocean-3']


@pytest.mark.asyncio
async def test_execute_naval_movement_phase_rejects_invalid(db_conn, test_server):
    """Test naval movement phase rejects invalid orders."""
    # Setup
    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Create mixed territories
    ocean = Territory(territory_id='ocean-1', terrain_type='ocean', guild_id=TEST_GUILD_ID)
    await ocean.upsert(db_conn)
    land = Territory(territory_id='plains-1', terrain_type='plains', guild_id=TEST_GUILD_ID)
    await land.upsert(db_conn)

    unit_type = UnitType(type_id='fleet', is_naval=True, movement=3, guild_id=TEST_GUILD_ID)
    await unit_type.upsert(db_conn)

    char = Character(identifier='c1', name='Captain', user_id=1, channel_id=999000000000000001, guild_id=TEST_GUILD_ID)
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, 'c1', TEST_GUILD_ID)

    unit = Unit(
        unit_id='fleet-1', unit_type='fleet', owner_character_id=char.id,
        current_territory_id='ocean-1', is_naval=True, movement=3, status='ACTIVE', guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, 'fleet-1', TEST_GUILD_ID)

    await NavalUnitPosition.set_positions(db_conn, unit.id, ['ocean-1'], TEST_GUILD_ID)

    # Create invalid order (path contains land)
    order = Order(
        order_id='order-1',
        order_type=OrderType.UNIT.value,
        character_id=char.id,
        unit_ids=[unit.id],
        status=OrderStatus.PENDING.value,
        phase=TurnPhase.MOVEMENT.value,
        order_data={'action': 'naval_convoy', 'path': ['ocean-1', 'plains-1']},
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute phase
    events = await execute_naval_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify order failed
    updated_order = await Order.fetch_by_order_id(db_conn, 'order-1', TEST_GUILD_ID)
    assert updated_order.status == OrderStatus.FAILED.value
    assert 'not a water territory' in updated_order.result_data.get('error', '')

    # Verify event generated
    failed_events = [e for e in events if e.event_type == 'ORDER_FAILED']
    assert len(failed_events) == 1
