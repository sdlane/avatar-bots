"""
Pytest tests for the land unit movement phase in turn resolution.

Tests verify:
- Basic movement (single unit, multiple steps, group movement)
- Movement bonuses (+1 for transit/transport)
- Terrain costs (mountains=3, desert=2, default=1)
- Multi-turn persistence
- Tick priority ordering
- Validation (co-location, naval exclusion)
- Patrol looping and speed limits
- Event generation
- Engagement detection

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_movement_phase.py -v
"""
import pytest
from datetime import datetime
from handlers.turn_handlers import execute_movement_phase
from handlers.movement_handlers import (
    calculate_movement_points,
    get_terrain_cost,
    build_movement_states,
    validate_units_colocation,
    get_unit_group_faction_id,
    are_factions_at_war,
    are_factions_allied,
    are_unit_groups_hostile,
    check_engagement,
)
from db import Character, Unit, Territory, Order, WargameConfig, Faction, War, WarParticipant, Alliance
from order_types import OrderType, OrderStatus, TurnPhase, ORDER_PHASE_MAP, ORDER_PRIORITY_MAP
from orders.movement_state import MovementUnitState, MovementStatus
from tests.conftest import TEST_GUILD_ID
from event_logging.movement_events import (
    transit_complete_character_line,
    transit_complete_gm_line,
    transit_progress_character_line,
    transit_progress_gm_line,
    movement_blocked_character_line,
    movement_blocked_gm_line,
    engagement_detected_character_line,
    engagement_detected_gm_line,
)


# ============================================================================
# Basic Movement Tests
# ============================================================================

@pytest.mark.asyncio
async def test_single_unit_transit_one_step(db_conn, test_server):
    """Test a single unit transiting one step."""
    # Setup: Create character
    character = Character(
        identifier="move-char-1", name="Movement Tester",
        channel_id=999000000000000001, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-1", TEST_GUILD_ID)

    # Setup: Create territories
    t1 = Territory(territory_id="T1", name="Territory 1", terrain_type="plains", guild_id=TEST_GUILD_ID)
    t2 = Territory(territory_id="T2", name="Territory 2", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    await t2.upsert(db_conn)

    # Setup: Create unit at T1 with movement=2
    unit = Unit(
        unit_id="unit-move-1", name="Moving Unit", unit_type="infantry",
        owner_character_id=character.id,
        movement=2, organization=10, max_organization=10,
        current_territory_id="T1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-move-1", TEST_GUILD_ID)

    # Setup: Create wargame config
    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Setup: Create transit order
    order = Order(
        order_id="order-move-1",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={
            'action': 'transit',
            'path': ['T1', 'T2'],
            'path_index': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute movement phase
    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify: Unit moved to T2
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-move-1", TEST_GUILD_ID)
    assert updated_unit.current_territory_id == "T2"

    # Verify: Order completed
    updated_order = await Order.fetch_by_order_id(db_conn, "order-move-1", TEST_GUILD_ID)
    assert updated_order.status == OrderStatus.SUCCESS.value
    assert updated_order.result_data['completed'] == True
    assert updated_order.result_data['final_territory'] == "T2"

    # Verify: TRANSIT_COMPLETE event generated
    transit_events = [e for e in events if e.event_type == 'TRANSIT_COMPLETE']
    assert len(transit_events) == 1
    assert transit_events[0].event_data['final_territory'] == "T2"
    assert 'unit-move-1' in transit_events[0].event_data['units']


@pytest.mark.asyncio
async def test_single_unit_multiple_steps_within_movement(db_conn, test_server):
    """Test a unit moving multiple steps in one turn."""
    # Setup
    character = Character(
        identifier="move-char-2", name="Multi Step Tester",
        channel_id=999000000000000002, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-2", TEST_GUILD_ID)

    # Create territories
    for i in range(1, 5):
        t = Territory(territory_id=f"MS{i}", name=f"Multi Step {i}", terrain_type="plains", guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    # Create unit with movement=3 (+ transit bonus = 4 total MP)
    unit = Unit(
        unit_id="unit-multi-step", name="Fast Unit", unit_type="cavalry",
        owner_character_id=character.id,
        movement=3, organization=10, max_organization=10,
        current_territory_id="MS1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-multi-step", TEST_GUILD_ID)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Transit order through 4 territories
    order = Order(
        order_id="order-multi-step",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={
            'action': 'transit',
            'path': ['MS1', 'MS2', 'MS3', 'MS4'],
            'path_index': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify: Unit reached MS4 (3 steps: MS1->MS2->MS3->MS4, cost 3, have 4 MP)
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-multi-step", TEST_GUILD_ID)
    assert updated_unit.current_territory_id == "MS4"

    # Verify: Order completed
    updated_order = await Order.fetch_by_order_id(db_conn, "order-multi-step", TEST_GUILD_ID)
    assert updated_order.status == OrderStatus.SUCCESS.value


@pytest.mark.asyncio
async def test_group_movement_uses_slowest_unit(db_conn, test_server):
    """Test that group movement uses the slowest unit's movement stat."""
    character = Character(
        identifier="move-char-3", name="Group Tester",
        channel_id=999000000000000003, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-3", TEST_GUILD_ID)

    # Create territories
    for i in range(1, 4):
        t = Territory(territory_id=f"G{i}", name=f"Group {i}", terrain_type="plains", guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    # Create fast unit (movement=4) and slow unit (movement=1)
    fast_unit = Unit(
        unit_id="unit-fast", name="Fast Unit", unit_type="cavalry",
        owner_character_id=character.id,
        movement=4, organization=10, max_organization=10,
        current_territory_id="G1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await fast_unit.upsert(db_conn)
    fast_unit = await Unit.fetch_by_unit_id(db_conn, "unit-fast", TEST_GUILD_ID)

    slow_unit = Unit(
        unit_id="unit-slow", name="Slow Unit", unit_type="siege",
        owner_character_id=character.id,
        movement=1, organization=10, max_organization=10,
        current_territory_id="G1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await slow_unit.upsert(db_conn)
    slow_unit = await Unit.fetch_by_unit_id(db_conn, "unit-slow", TEST_GUILD_ID)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Group transit order (movement = min(4,1) + 1 bonus = 2 MP)
    order = Order(
        order_id="order-group",
        order_type=OrderType.UNIT.value,
        unit_ids=[fast_unit.id, slow_unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={
            'action': 'transit',
            'path': ['G1', 'G2', 'G3'],
            'path_index': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute
    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify: Both units moved to G3 (2 steps, 2 MP available)
    updated_fast = await Unit.fetch_by_unit_id(db_conn, "unit-fast", TEST_GUILD_ID)
    updated_slow = await Unit.fetch_by_unit_id(db_conn, "unit-slow", TEST_GUILD_ID)
    assert updated_fast.current_territory_id == "G3"
    assert updated_slow.current_territory_id == "G3"


@pytest.mark.asyncio
async def test_transit_bonus_applied(db_conn, test_server):
    """Test that +1 movement bonus is applied for transit action."""
    character = Character(
        identifier="move-char-bonus", name="Bonus Tester",
        channel_id=999000000000000004, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-bonus", TEST_GUILD_ID)

    for i in range(1, 4):
        t = Territory(territory_id=f"B{i}", name=f"Bonus {i}", terrain_type="plains", guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    # Unit with movement=1, with transit bonus = 2 total MP
    unit = Unit(
        unit_id="unit-bonus", name="Bonus Unit", unit_type="infantry",
        owner_character_id=character.id,
        movement=1, organization=10, max_organization=10,
        current_territory_id="B1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-bonus", TEST_GUILD_ID)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    order = Order(
        order_id="order-bonus",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={
            'action': 'transit',  # +1 bonus
            'path': ['B1', 'B2', 'B3'],
            'path_index': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Should reach B3 (2 steps with 2 MP)
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-bonus", TEST_GUILD_ID)
    assert updated_unit.current_territory_id == "B3"


@pytest.mark.asyncio
async def test_patrol_no_bonus(db_conn, test_server):
    """Test that patrol action does not get +1 movement bonus."""
    character = Character(
        identifier="move-char-patrol-nb", name="Patrol No Bonus",
        channel_id=999000000000000005, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-patrol-nb", TEST_GUILD_ID)

    for i in range(1, 4):
        t = Territory(territory_id=f"PNB{i}", name=f"Patrol NB {i}", terrain_type="plains", guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    # Unit with movement=1, patrol has no bonus = 1 total MP
    unit = Unit(
        unit_id="unit-patrol-nb", name="Patrol NB Unit", unit_type="infantry",
        owner_character_id=character.id,
        movement=1, organization=10, max_organization=10,
        current_territory_id="PNB1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-patrol-nb", TEST_GUILD_ID)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    order = Order(
        order_id="order-patrol-nb",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={
            'action': 'patrol',  # No bonus
            'path': ['PNB1', 'PNB2', 'PNB3'],
            'path_index': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Should only reach PNB2 (1 step with 1 MP, no bonus)
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-patrol-nb", TEST_GUILD_ID)
    assert updated_unit.current_territory_id == "PNB2"


# ============================================================================
# Terrain Cost Tests
# ============================================================================

@pytest.mark.asyncio
async def test_terrain_mountains_cost_3(db_conn, test_server):
    """Test that mountains terrain costs 3 MP."""
    character = Character(
        identifier="move-char-mountain", name="Mountain Tester",
        channel_id=999000000000000006, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-mountain", TEST_GUILD_ID)

    t1 = Territory(territory_id="MT1", name="Plains", terrain_type="plains", guild_id=TEST_GUILD_ID)
    t2 = Territory(territory_id="MT2", name="Mountains", terrain_type="mountains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    await t2.upsert(db_conn)

    # Unit with movement=2 + bonus = 3 MP, exactly enough for mountains
    unit = Unit(
        unit_id="unit-mountain", name="Mountain Climber", unit_type="infantry",
        owner_character_id=character.id,
        movement=2, organization=10, max_organization=10,
        current_territory_id="MT1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-mountain", TEST_GUILD_ID)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    order = Order(
        order_id="order-mountain",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={
            'action': 'transit',
            'path': ['MT1', 'MT2'],
            'path_index': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Should reach MT2 (3 MP for mountains, have 3)
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-mountain", TEST_GUILD_ID)
    assert updated_unit.current_territory_id == "MT2"


@pytest.mark.asyncio
async def test_terrain_desert_cost_2(db_conn, test_server):
    """Test that desert terrain costs 2 MP."""
    character = Character(
        identifier="move-char-desert", name="Desert Tester",
        channel_id=999000000000000007, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-desert", TEST_GUILD_ID)

    t1 = Territory(territory_id="DT1", name="Plains", terrain_type="plains", guild_id=TEST_GUILD_ID)
    t2 = Territory(territory_id="DT2", name="Desert", terrain_type="desert", guild_id=TEST_GUILD_ID)
    t3 = Territory(territory_id="DT3", name="Plains Again", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    await t2.upsert(db_conn)
    await t3.upsert(db_conn)

    # Unit with movement=2 + bonus = 3 MP
    unit = Unit(
        unit_id="unit-desert", name="Desert Walker", unit_type="infantry",
        owner_character_id=character.id,
        movement=2, organization=10, max_organization=10,
        current_territory_id="DT1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-desert", TEST_GUILD_ID)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    order = Order(
        order_id="order-desert",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={
            'action': 'transit',
            'path': ['DT1', 'DT2', 'DT3'],
            'path_index': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # DT1->DT2 costs 2, DT2->DT3 costs 1 = 3 total, have 3 MP
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-desert", TEST_GUILD_ID)
    assert updated_unit.current_territory_id == "DT3"


@pytest.mark.asyncio
async def test_blocked_by_terrain_cost(db_conn, test_server):
    """Test that unit is blocked when terrain cost > remaining MP."""
    character = Character(
        identifier="move-char-blocked", name="Blocked Tester",
        channel_id=999000000000000008, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-blocked", TEST_GUILD_ID)

    t1 = Territory(territory_id="BL1", name="Start", terrain_type="plains", guild_id=TEST_GUILD_ID)
    t2 = Territory(territory_id="BL2", name="Mountains", terrain_type="mountains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    await t2.upsert(db_conn)

    # Unit with movement=1 + bonus = 2 MP, not enough for mountains (cost 3)
    unit = Unit(
        unit_id="unit-blocked", name="Blocked Unit", unit_type="infantry",
        owner_character_id=character.id,
        movement=1, organization=10, max_organization=10,
        current_territory_id="BL1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-blocked", TEST_GUILD_ID)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    order = Order(
        order_id="order-blocked",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={
            'action': 'transit',
            'path': ['BL1', 'BL2'],
            'path_index': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Unit should stay at BL1
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-blocked", TEST_GUILD_ID)
    assert updated_unit.current_territory_id == "BL1"

    # Order should be ONGOING (not complete)
    updated_order = await Order.fetch_by_order_id(db_conn, "order-blocked", TEST_GUILD_ID)
    assert updated_order.status == OrderStatus.ONGOING.value
    assert updated_order.result_data['blocked'] == True

    # MOVEMENT_BLOCKED event should be generated
    blocked_events = [e for e in events if e.event_type == 'MOVEMENT_BLOCKED']
    assert len(blocked_events) == 1
    assert blocked_events[0].event_data['blocked_at'] == "BL2"
    assert blocked_events[0].event_data['terrain_cost'] == 3
    assert blocked_events[0].event_data['remaining_mp'] == 2


# ============================================================================
# Multi-Turn Persistence Tests
# ============================================================================

@pytest.mark.asyncio
async def test_multi_turn_path_persistence(db_conn, test_server):
    """Test that path_index persists across turns for ongoing orders."""
    character = Character(
        identifier="move-char-multi", name="Multi Turn Tester",
        channel_id=999000000000000009, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-multi", TEST_GUILD_ID)

    # Create 5 territories
    for i in range(1, 6):
        t = Territory(territory_id=f"MT{i}", name=f"Multi {i}", terrain_type="plains", guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    # Unit with movement=1 + bonus = 2 MP per turn
    unit = Unit(
        unit_id="unit-multi-turn", name="Slow Unit", unit_type="infantry",
        owner_character_id=character.id,
        movement=1, organization=10, max_organization=10,
        current_territory_id="MT1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-multi-turn", TEST_GUILD_ID)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Path of 5 territories (4 steps, 2 per turn = 2 turns)
    order = Order(
        order_id="order-multi-turn",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={
            'action': 'transit',
            'path': ['MT1', 'MT2', 'MT3', 'MT4', 'MT5'],
            'path_index': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Turn 1
    events1 = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # After turn 1: Should be at MT3 (2 steps)
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-multi-turn", TEST_GUILD_ID)
    assert updated_unit.current_territory_id == "MT3"

    updated_order = await Order.fetch_by_order_id(db_conn, "order-multi-turn", TEST_GUILD_ID)
    assert updated_order.status == OrderStatus.ONGOING.value
    assert updated_order.result_data['path_index'] == 2

    # TRANSIT_PROGRESS should be generated
    progress_events = [e for e in events1 if e.event_type == 'TRANSIT_PROGRESS']
    assert len(progress_events) == 1

    # Turn 2
    events2 = await execute_movement_phase(db_conn, TEST_GUILD_ID, 2)

    # After turn 2: Should be at MT5 (completed)
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-multi-turn", TEST_GUILD_ID)
    assert updated_unit.current_territory_id == "MT5"

    updated_order = await Order.fetch_by_order_id(db_conn, "order-multi-turn", TEST_GUILD_ID)
    assert updated_order.status == OrderStatus.SUCCESS.value
    assert updated_order.result_data['completed'] == True

    # TRANSIT_COMPLETE should be generated
    complete_events = [e for e in events2 if e.event_type == 'TRANSIT_COMPLETE']
    assert len(complete_events) == 1


# ============================================================================
# Tick Priority Ordering Tests
# ============================================================================

@pytest.mark.asyncio
async def test_faster_units_move_first(db_conn, test_server):
    """Test that units with higher MP move first at each tick."""
    character = Character(
        identifier="move-char-priority", name="Priority Tester",
        channel_id=999000000000000010, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-priority", TEST_GUILD_ID)

    # Create territories
    t1 = Territory(territory_id="PR1", name="Start", terrain_type="plains", guild_id=TEST_GUILD_ID)
    t2 = Territory(territory_id="PR2", name="End", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    await t2.upsert(db_conn)

    # Fast unit (movement=3 + bonus = 4)
    fast_unit = Unit(
        unit_id="unit-priority-fast", name="Fast", unit_type="cavalry",
        owner_character_id=character.id,
        movement=3, organization=10, max_organization=10,
        current_territory_id="PR1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await fast_unit.upsert(db_conn)
    fast_unit = await Unit.fetch_by_unit_id(db_conn, "unit-priority-fast", TEST_GUILD_ID)

    # Slow unit (movement=1 + bonus = 2)
    slow_unit = Unit(
        unit_id="unit-priority-slow", name="Slow", unit_type="infantry",
        owner_character_id=character.id,
        movement=1, organization=10, max_organization=10,
        current_territory_id="PR1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await slow_unit.upsert(db_conn)
    slow_unit = await Unit.fetch_by_unit_id(db_conn, "unit-priority-slow", TEST_GUILD_ID)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Create orders (slow submitted first but fast should move first at higher ticks)
    slow_order = Order(
        order_id="order-priority-slow",
        order_type=OrderType.UNIT.value,
        unit_ids=[slow_unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={'action': 'transit', 'path': ['PR1', 'PR2'], 'path_index': 0},
        submitted_at=datetime(2024, 1, 1, 10, 0, 0),  # Earlier
        guild_id=TEST_GUILD_ID
    )
    await slow_order.upsert(db_conn)

    fast_order = Order(
        order_id="order-priority-fast",
        order_type=OrderType.UNIT.value,
        unit_ids=[fast_unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={'action': 'transit', 'path': ['PR1', 'PR2'], 'path_index': 0},
        submitted_at=datetime(2024, 1, 1, 11, 0, 0),  # Later
        guild_id=TEST_GUILD_ID
    )
    await fast_order.upsert(db_conn)

    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Both should reach PR2
    updated_fast = await Unit.fetch_by_unit_id(db_conn, "unit-priority-fast", TEST_GUILD_ID)
    updated_slow = await Unit.fetch_by_unit_id(db_conn, "unit-priority-slow", TEST_GUILD_ID)
    assert updated_fast.current_territory_id == "PR2"
    assert updated_slow.current_territory_id == "PR2"


# ============================================================================
# Validation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_units_not_colocated_fails_order(db_conn, test_server):
    """Test that order fails if units are not in the same territory."""
    character = Character(
        identifier="move-char-coloc", name="Coloc Tester",
        channel_id=999000000000000011, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-coloc", TEST_GUILD_ID)

    t1 = Territory(territory_id="CL1", name="Location 1", terrain_type="plains", guild_id=TEST_GUILD_ID)
    t2 = Territory(territory_id="CL2", name="Location 2", terrain_type="plains", guild_id=TEST_GUILD_ID)
    t3 = Territory(territory_id="CL3", name="Destination", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    await t2.upsert(db_conn)
    await t3.upsert(db_conn)

    # Units in different territories
    unit1 = Unit(
        unit_id="unit-coloc-1", name="Unit 1", unit_type="infantry",
        owner_character_id=character.id,
        movement=2, organization=10, max_organization=10,
        current_territory_id="CL1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit1.upsert(db_conn)
    unit1 = await Unit.fetch_by_unit_id(db_conn, "unit-coloc-1", TEST_GUILD_ID)

    unit2 = Unit(
        unit_id="unit-coloc-2", name="Unit 2", unit_type="infantry",
        owner_character_id=character.id,
        movement=2, organization=10, max_organization=10,
        current_territory_id="CL2", is_naval=False,  # Different territory!
        guild_id=TEST_GUILD_ID
    )
    await unit2.upsert(db_conn)
    unit2 = await Unit.fetch_by_unit_id(db_conn, "unit-coloc-2", TEST_GUILD_ID)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    order = Order(
        order_id="order-coloc",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit1.id, unit2.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={'action': 'transit', 'path': ['CL1', 'CL3'], 'path_index': 0},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Order should fail
    updated_order = await Order.fetch_by_order_id(db_conn, "order-coloc", TEST_GUILD_ID)
    assert updated_order.status == OrderStatus.FAILED.value
    assert 'not co-located' in updated_order.result_data['error']

    # ORDER_FAILED event should be generated
    failed_events = [e for e in events if e.event_type == 'ORDER_FAILED']
    assert len(failed_events) == 1


@pytest.mark.asyncio
async def test_naval_units_excluded(db_conn, test_server):
    """Test that naval units are excluded from land movement orders."""
    character = Character(
        identifier="move-char-naval", name="Naval Tester",
        channel_id=999000000000000012, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-naval", TEST_GUILD_ID)

    t1 = Territory(territory_id="NV1", name="Coast", terrain_type="coast", guild_id=TEST_GUILD_ID)
    t2 = Territory(territory_id="NV2", name="Inland", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    await t2.upsert(db_conn)

    # Naval unit
    naval_unit = Unit(
        unit_id="unit-naval", name="Ship", unit_type="ship",
        owner_character_id=character.id,
        movement=4, organization=10, max_organization=10,
        current_territory_id="NV1", is_naval=True,  # Naval!
        guild_id=TEST_GUILD_ID
    )
    await naval_unit.upsert(db_conn)
    naval_unit = await Unit.fetch_by_unit_id(db_conn, "unit-naval", TEST_GUILD_ID)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    order = Order(
        order_id="order-naval",
        order_type=OrderType.UNIT.value,
        unit_ids=[naval_unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={'action': 'transit', 'path': ['NV1', 'NV2'], 'path_index': 0},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Order should fail (no valid land units)
    updated_order = await Order.fetch_by_order_id(db_conn, "order-naval", TEST_GUILD_ID)
    assert updated_order.status == OrderStatus.FAILED.value

    # Naval unit should not move
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-naval", TEST_GUILD_ID)
    assert updated_unit.current_territory_id == "NV1"


# ============================================================================
# Patrol Tests
# ============================================================================

@pytest.mark.asyncio
async def test_patrol_loops_indefinitely(db_conn, test_server):
    """Test that patrol orders loop back to the start of the path."""
    character = Character(
        identifier="move-char-patrol", name="Patrol Tester",
        channel_id=999000000000000013, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-patrol", TEST_GUILD_ID)

    for i in range(1, 4):
        t = Territory(territory_id=f"PT{i}", name=f"Patrol {i}", terrain_type="plains", guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    # Unit with movement=3 (no bonus = 3 MP, enough to complete path and start over)
    unit = Unit(
        unit_id="unit-patrol", name="Patrol Unit", unit_type="cavalry",
        owner_character_id=character.id,
        movement=3, organization=10, max_organization=10,
        current_territory_id="PT1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-patrol", TEST_GUILD_ID)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    order = Order(
        order_id="order-patrol",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={
            'action': 'patrol',
            'path': ['PT1', 'PT2', 'PT3'],
            'path_index': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Patrol should remain ONGOING (never completes)
    updated_order = await Order.fetch_by_order_id(db_conn, "order-patrol", TEST_GUILD_ID)
    assert updated_order.status == OrderStatus.ONGOING.value

    # TRANSIT_PROGRESS (not TRANSIT_COMPLETE) should be generated
    progress_events = [e for e in events if e.event_type == 'TRANSIT_PROGRESS']
    complete_events = [e for e in events if e.event_type == 'TRANSIT_COMPLETE']
    assert len(progress_events) == 1
    assert len(complete_events) == 0


@pytest.mark.asyncio
async def test_patrol_speed_limits_movement(db_conn, test_server):
    """Test that patrol speed parameter limits MP expenditure per turn."""
    character = Character(
        identifier="move-char-patrol-speed", name="Patrol Speed Tester",
        channel_id=999000000000000014, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-patrol-speed", TEST_GUILD_ID)

    for i in range(1, 5):
        t = Territory(territory_id=f"PS{i}", name=f"Patrol Speed {i}", terrain_type="plains", guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    # Unit with movement=4 (no bonus = 4 MP)
    unit = Unit(
        unit_id="unit-patrol-speed", name="Slow Patrol", unit_type="cavalry",
        owner_character_id=character.id,
        movement=4, organization=10, max_organization=10,
        current_territory_id="PS1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-patrol-speed", TEST_GUILD_ID)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Patrol with speed=2 (only expend 2 MP per turn despite having 4)
    order = Order(
        order_id="order-patrol-speed",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={
            'action': 'patrol',
            'path': ['PS1', 'PS2', 'PS3', 'PS4'],
            'path_index': 0,
            'speed': 2
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Should only move 2 steps (speed limit), ending at PS3
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-patrol-speed", TEST_GUILD_ID)
    assert updated_unit.current_territory_id == "PS3"


# ============================================================================
# Event Generation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_transit_progress_event_generated(db_conn, test_server):
    """Test that TRANSIT_PROGRESS event is generated for incomplete paths."""
    character = Character(
        identifier="move-char-progress", name="Progress Tester",
        channel_id=999000000000000015, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-progress", TEST_GUILD_ID)

    for i in range(1, 5):
        t = Territory(territory_id=f"PG{i}", name=f"Progress {i}", terrain_type="plains", guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    unit = Unit(
        unit_id="unit-progress", name="Progress Unit", unit_type="infantry",
        owner_character_id=character.id,
        movement=1, organization=10, max_organization=10,
        current_territory_id="PG1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-progress", TEST_GUILD_ID)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    order = Order(
        order_id="order-progress",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={
            'action': 'transit',
            'path': ['PG1', 'PG2', 'PG3', 'PG4'],
            'path_index': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    progress_events = [e for e in events if e.event_type == 'TRANSIT_PROGRESS']
    assert len(progress_events) == 1
    event = progress_events[0]
    assert event.event_data['units'] == ['unit-progress']
    assert event.event_data['path_index'] == 2
    assert event.event_data['total_steps'] == 3
    assert character.id in event.event_data['affected_character_ids']


@pytest.mark.asyncio
async def test_transit_complete_event_generated(db_conn, test_server):
    """Test that TRANSIT_COMPLETE event is generated for completed paths."""
    character = Character(
        identifier="move-char-complete", name="Complete Tester",
        channel_id=999000000000000016, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "move-char-complete", TEST_GUILD_ID)

    for i in range(1, 3):
        t = Territory(territory_id=f"CP{i}", name=f"Complete {i}", terrain_type="plains", guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

    unit = Unit(
        unit_id="unit-complete", name="Complete Unit", unit_type="cavalry",
        owner_character_id=character.id,
        movement=3, organization=10, max_organization=10,
        current_territory_id="CP1", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-complete", TEST_GUILD_ID)

    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    order = Order(
        order_id="order-complete",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit.id],
        character_id=character.id,
        turn_number=1,
        phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={
            'action': 'transit',
            'path': ['CP1', 'CP2'],
            'path_index': 0
        },
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    complete_events = [e for e in events if e.event_type == 'TRANSIT_COMPLETE']
    assert len(complete_events) == 1
    event = complete_events[0]
    assert event.event_data['units'] == ['unit-complete']
    assert event.event_data['final_territory'] == 'CP2'
    assert character.id in event.event_data['affected_character_ids']


# ============================================================================
# Event Formatting Tests
# ============================================================================

def test_transit_complete_character_line_format():
    """Test TRANSIT_COMPLETE character line formatting."""
    event_data = {
        'units': ['unit-1', 'unit-2'],
        'final_territory': 'T5',
        'affected_character_ids': [123]
    }
    line = transit_complete_character_line(event_data)
    assert 'unit-1' in line
    assert 'unit-2' in line
    assert 'T5' in line


def test_transit_progress_character_line_format():
    """Test TRANSIT_PROGRESS character line formatting."""
    event_data = {
        'units': ['unit-1'],
        'current_territory': 'T3',
        'path_index': 2,
        'total_steps': 4,
        'affected_character_ids': [123]
    }
    line = transit_progress_character_line(event_data)
    assert 'unit-1' in line
    assert 'T3' in line
    assert '2/4' in line


def test_movement_blocked_character_line_format():
    """Test MOVEMENT_BLOCKED character line formatting."""
    event_data = {
        'units': ['unit-1'],
        'blocked_at': 'T_MOUNTAINS',
        'terrain_cost': 3,
        'remaining_mp': 2,
        'current_territory': 'T_PLAINS',
        'affected_character_ids': [123]
    }
    line = movement_blocked_character_line(event_data)
    assert 'unit-1' in line
    assert 'T_MOUNTAINS' in line
    assert 'cost 3' in line
    assert '2 MP' in line


def test_movement_blocked_gm_line_format():
    """Test MOVEMENT_BLOCKED GM line formatting."""
    event_data = {
        'units': ['unit-1'],
        'blocked_at': 'T_MOUNTAINS',
        'terrain_cost': 3,
        'remaining_mp': 2,
        'affected_character_ids': [123]
    }
    line = movement_blocked_gm_line(event_data)
    assert 'unit-1' in line
    assert 'T_MOUNTAINS' in line
    assert '3' in line
    assert '2' in line


# ============================================================================
# Helper Function Unit Tests
# ============================================================================

def test_calculate_movement_points_transit():
    """Test MP calculation with transit bonus."""
    units = [
        Unit(unit_id="u1", unit_type="infantry", movement=2, owner_character_id=1, guild_id=TEST_GUILD_ID),
        Unit(unit_id="u2", unit_type="infantry", movement=3, owner_character_id=1, guild_id=TEST_GUILD_ID),
    ]
    # Slowest is 2, transit adds +1 = 3
    mp = calculate_movement_points(units, "transit")
    assert mp == 3


def test_calculate_movement_points_patrol():
    """Test MP calculation without bonus for patrol."""
    units = [
        Unit(unit_id="u1", unit_type="infantry", movement=2, owner_character_id=1, guild_id=TEST_GUILD_ID),
    ]
    # No bonus for patrol
    mp = calculate_movement_points(units, "patrol")
    assert mp == 2


def test_calculate_movement_points_transport():
    """Test MP calculation with transport bonus."""
    units = [
        Unit(unit_id="u1", unit_type="infantry", movement=1, owner_character_id=1, guild_id=TEST_GUILD_ID),
    ]
    # Transport also gets +1
    mp = calculate_movement_points(units, "transport")
    assert mp == 2


@pytest.mark.asyncio
async def test_get_terrain_cost_plains(db_conn, test_server):
    """Test terrain cost for plains is 1."""
    t = Territory(territory_id="TC_PLAINS", name="Plains", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t.upsert(db_conn)

    cost = await get_terrain_cost(db_conn, "TC_PLAINS", TEST_GUILD_ID)
    assert cost == 1


@pytest.mark.asyncio
async def test_get_terrain_cost_mountains(db_conn, test_server):
    """Test terrain cost for mountains is 3."""
    t = Territory(territory_id="TC_MOUNT", name="Mountains", terrain_type="mountains", guild_id=TEST_GUILD_ID)
    await t.upsert(db_conn)

    cost = await get_terrain_cost(db_conn, "TC_MOUNT", TEST_GUILD_ID)
    assert cost == 3


@pytest.mark.asyncio
async def test_get_terrain_cost_desert(db_conn, test_server):
    """Test terrain cost for desert is 2."""
    t = Territory(territory_id="TC_DESERT", name="Desert", terrain_type="desert", guild_id=TEST_GUILD_ID)
    await t.upsert(db_conn)

    cost = await get_terrain_cost(db_conn, "TC_DESERT", TEST_GUILD_ID)
    assert cost == 2


@pytest.mark.asyncio
async def test_no_unit_orders_returns_empty(db_conn, test_server):
    """Test that execute_movement_phase returns empty when no orders exist."""
    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)
    assert events == []


# ============================================================================
# Engagement Detection Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_unit_group_faction_id_character_owned(db_conn, test_server):
    """Test that character-owned units return owner's represented_faction_id."""
    # Create faction
    faction = Faction(
        faction_id="test-faction-1", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction-1", TEST_GUILD_ID)

    # Create character with represented faction
    character = Character(
        identifier="eng-char-1", name="Engagement Tester",
        channel_id=999000000000000100,
        represented_faction_id=faction.id,
        guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "eng-char-1", TEST_GUILD_ID)

    # Create unit owned by character
    unit = Unit(
        unit_id="unit-eng-1", name="Test Unit", unit_type="infantry",
        owner_character_id=character.id,
        movement=2, guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-eng-1", TEST_GUILD_ID)

    # Get faction ID
    result = await get_unit_group_faction_id(db_conn, [unit], TEST_GUILD_ID)
    assert result == faction.id


@pytest.mark.asyncio
async def test_get_unit_group_faction_id_faction_owned(db_conn, test_server):
    """Test that faction-owned units return owner_faction_id."""
    # Create faction
    faction = Faction(
        faction_id="test-faction-2", name="Test Faction 2",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction-2", TEST_GUILD_ID)

    # Create unit owned by faction
    unit = Unit(
        unit_id="unit-eng-2", name="Faction Unit", unit_type="infantry",
        owner_faction_id=faction.id,
        movement=2, guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-eng-2", TEST_GUILD_ID)

    # Get faction ID
    result = await get_unit_group_faction_id(db_conn, [unit], TEST_GUILD_ID)
    assert result == faction.id


@pytest.mark.asyncio
async def test_get_unit_group_faction_id_no_faction(db_conn, test_server):
    """Test that character without represented faction returns None."""
    # Create character without represented faction
    character = Character(
        identifier="eng-char-no-faction", name="No Faction Char",
        channel_id=999000000000000101,
        guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "eng-char-no-faction", TEST_GUILD_ID)

    # Create unit owned by character
    unit = Unit(
        unit_id="unit-eng-no-faction", name="Test Unit", unit_type="infantry",
        owner_character_id=character.id,
        movement=2, guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-eng-no-faction", TEST_GUILD_ID)

    # Get faction ID
    result = await get_unit_group_faction_id(db_conn, [unit], TEST_GUILD_ID)
    assert result is None


@pytest.mark.asyncio
async def test_are_factions_at_war_opposite_sides(db_conn, test_server):
    """Test that factions on opposite sides of a war are detected as at war."""
    # Create two factions
    faction_a = Faction(faction_id="war-faction-a", name="Faction A", guild_id=TEST_GUILD_ID)
    faction_b = Faction(faction_id="war-faction-b", name="Faction B", guild_id=TEST_GUILD_ID)
    await faction_a.upsert(db_conn)
    await faction_b.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, "war-faction-a", TEST_GUILD_ID)
    faction_b = await Faction.fetch_by_faction_id(db_conn, "war-faction-b", TEST_GUILD_ID)

    # Create a war
    war = War(war_id="WAR-TEST-01", objective="Test War", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war.upsert(db_conn)
    war = await War.fetch_by_id(db_conn, "WAR-TEST-01", TEST_GUILD_ID)

    # Add factions to opposite sides
    participant_a = WarParticipant(
        war_id=war.id, faction_id=faction_a.id, side="SIDE_A",
        joined_turn=1, is_original_declarer=True, guild_id=TEST_GUILD_ID
    )
    participant_b = WarParticipant(
        war_id=war.id, faction_id=faction_b.id, side="SIDE_B",
        joined_turn=1, is_original_declarer=False, guild_id=TEST_GUILD_ID
    )
    await participant_a.insert(db_conn)
    await participant_b.insert(db_conn)

    # Check if at war
    result = await are_factions_at_war(db_conn, faction_a.id, faction_b.id, TEST_GUILD_ID)
    assert result is True


@pytest.mark.asyncio
async def test_are_factions_at_war_same_side(db_conn, test_server):
    """Test that factions on the same side of a war are not detected as at war."""
    # Create two factions
    faction_a = Faction(faction_id="ally-faction-a", name="Ally A", guild_id=TEST_GUILD_ID)
    faction_b = Faction(faction_id="ally-faction-b", name="Ally B", guild_id=TEST_GUILD_ID)
    await faction_a.upsert(db_conn)
    await faction_b.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, "ally-faction-a", TEST_GUILD_ID)
    faction_b = await Faction.fetch_by_faction_id(db_conn, "ally-faction-b", TEST_GUILD_ID)

    # Create a war
    war = War(war_id="WAR-TEST-02", objective="Test War 2", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war.upsert(db_conn)
    war = await War.fetch_by_id(db_conn, "WAR-TEST-02", TEST_GUILD_ID)

    # Add factions to same side
    participant_a = WarParticipant(
        war_id=war.id, faction_id=faction_a.id, side="SIDE_A",
        joined_turn=1, is_original_declarer=True, guild_id=TEST_GUILD_ID
    )
    participant_b = WarParticipant(
        war_id=war.id, faction_id=faction_b.id, side="SIDE_A",
        joined_turn=1, is_original_declarer=False, guild_id=TEST_GUILD_ID
    )
    await participant_a.insert(db_conn)
    await participant_b.insert(db_conn)

    # Check if at war
    result = await are_factions_at_war(db_conn, faction_a.id, faction_b.id, TEST_GUILD_ID)
    assert result is False


@pytest.mark.asyncio
async def test_are_factions_at_war_no_war(db_conn, test_server):
    """Test that factions not in any shared war are not detected as at war."""
    # Create two factions
    faction_a = Faction(faction_id="peace-faction-a", name="Peace A", guild_id=TEST_GUILD_ID)
    faction_b = Faction(faction_id="peace-faction-b", name="Peace B", guild_id=TEST_GUILD_ID)
    await faction_a.upsert(db_conn)
    await faction_b.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, "peace-faction-a", TEST_GUILD_ID)
    faction_b = await Faction.fetch_by_faction_id(db_conn, "peace-faction-b", TEST_GUILD_ID)

    # Check if at war (no war exists)
    result = await are_factions_at_war(db_conn, faction_a.id, faction_b.id, TEST_GUILD_ID)
    assert result is False


@pytest.mark.asyncio
async def test_are_factions_allied_active(db_conn, test_server):
    """Test that factions with active alliance are detected as allied."""
    # Create two factions
    faction_a = Faction(faction_id="alliance-a", name="Alliance A", guild_id=TEST_GUILD_ID)
    faction_b = Faction(faction_id="alliance-b", name="Alliance B", guild_id=TEST_GUILD_ID)
    await faction_a.upsert(db_conn)
    await faction_b.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, "alliance-a", TEST_GUILD_ID)
    faction_b = await Faction.fetch_by_faction_id(db_conn, "alliance-b", TEST_GUILD_ID)

    # Create active alliance (ensure canonical ordering)
    min_id = min(faction_a.id, faction_b.id)
    max_id = max(faction_a.id, faction_b.id)
    alliance = Alliance(
        faction_a_id=min_id, faction_b_id=max_id,
        status="ACTIVE", initiated_by_faction_id=min_id,
        guild_id=TEST_GUILD_ID
    )
    await alliance.upsert(db_conn)

    # Check if allied
    result = await are_factions_allied(db_conn, faction_a.id, faction_b.id, TEST_GUILD_ID)
    assert result is True


@pytest.mark.asyncio
async def test_are_factions_allied_pending(db_conn, test_server):
    """Test that factions with pending alliance are not detected as allied."""
    # Create two factions
    faction_a = Faction(faction_id="pending-a", name="Pending A", guild_id=TEST_GUILD_ID)
    faction_b = Faction(faction_id="pending-b", name="Pending B", guild_id=TEST_GUILD_ID)
    await faction_a.upsert(db_conn)
    await faction_b.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, "pending-a", TEST_GUILD_ID)
    faction_b = await Faction.fetch_by_faction_id(db_conn, "pending-b", TEST_GUILD_ID)

    # Create pending alliance (ensure canonical ordering)
    min_id = min(faction_a.id, faction_b.id)
    max_id = max(faction_a.id, faction_b.id)
    alliance = Alliance(
        faction_a_id=min_id, faction_b_id=max_id,
        status="PENDING_FACTION_A", initiated_by_faction_id=min_id,
        guild_id=TEST_GUILD_ID
    )
    await alliance.upsert(db_conn)

    # Check if allied
    result = await are_factions_allied(db_conn, faction_a.id, faction_b.id, TEST_GUILD_ID)
    assert result is False


@pytest.mark.asyncio
async def test_are_factions_allied_no_alliance(db_conn, test_server):
    """Test that factions with no alliance are not detected as allied."""
    # Create two factions
    faction_a = Faction(faction_id="no-alliance-a", name="No Alliance A", guild_id=TEST_GUILD_ID)
    faction_b = Faction(faction_id="no-alliance-b", name="No Alliance B", guild_id=TEST_GUILD_ID)
    await faction_a.upsert(db_conn)
    await faction_b.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, "no-alliance-a", TEST_GUILD_ID)
    faction_b = await Faction.fetch_by_faction_id(db_conn, "no-alliance-b", TEST_GUILD_ID)

    # Check if allied (no alliance exists)
    result = await are_factions_allied(db_conn, faction_a.id, faction_b.id, TEST_GUILD_ID)
    assert result is False


@pytest.mark.asyncio
async def test_are_unit_groups_hostile_at_war(db_conn, test_server):
    """Test that unit groups from factions at war are hostile."""
    # Create two factions at war
    faction_a = Faction(faction_id="hostile-war-a", name="Hostile A", guild_id=TEST_GUILD_ID)
    faction_b = Faction(faction_id="hostile-war-b", name="Hostile B", guild_id=TEST_GUILD_ID)
    await faction_a.upsert(db_conn)
    await faction_b.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, "hostile-war-a", TEST_GUILD_ID)
    faction_b = await Faction.fetch_by_faction_id(db_conn, "hostile-war-b", TEST_GUILD_ID)

    # Create war
    war = War(war_id="WAR-HOSTILE-01", objective="Hostile Test", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war.upsert(db_conn)
    war = await War.fetch_by_id(db_conn, "WAR-HOSTILE-01", TEST_GUILD_ID)

    # Add to opposite sides
    await WarParticipant(war_id=war.id, faction_id=faction_a.id, side="SIDE_A", joined_turn=1, guild_id=TEST_GUILD_ID).insert(db_conn)
    await WarParticipant(war_id=war.id, faction_id=faction_b.id, side="SIDE_B", joined_turn=1, guild_id=TEST_GUILD_ID).insert(db_conn)

    # Create territory
    territory = Territory(territory_id="T-HOSTILE", name="Hostile Territory", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await territory.upsert(db_conn)

    # Create units
    unit_a = Unit(unit_id="unit-hostile-a", unit_type="infantry", owner_faction_id=faction_a.id, movement=2, guild_id=TEST_GUILD_ID)
    unit_b = Unit(unit_id="unit-hostile-b", unit_type="infantry", owner_faction_id=faction_b.id, movement=2, guild_id=TEST_GUILD_ID)
    await unit_a.upsert(db_conn)
    await unit_b.upsert(db_conn)
    unit_a = await Unit.fetch_by_unit_id(db_conn, "unit-hostile-a", TEST_GUILD_ID)
    unit_b = await Unit.fetch_by_unit_id(db_conn, "unit-hostile-b", TEST_GUILD_ID)

    # Check hostility
    is_hostile, reason = await are_unit_groups_hostile(
        db_conn, [unit_a], [unit_b], "T-HOSTILE", "transit", "transit", TEST_GUILD_ID
    )
    assert is_hostile is True
    assert reason == "war"


@pytest.mark.asyncio
async def test_are_unit_groups_hostile_same_faction(db_conn, test_server):
    """Test that unit groups from the same faction are not hostile."""
    # Create faction
    faction = Faction(faction_id="same-faction", name="Same Faction", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "same-faction", TEST_GUILD_ID)

    # Create territory
    territory = Territory(territory_id="T-SAME", name="Same Territory", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await territory.upsert(db_conn)

    # Create units from same faction
    unit_a = Unit(unit_id="unit-same-a", unit_type="infantry", owner_faction_id=faction.id, movement=2, guild_id=TEST_GUILD_ID)
    unit_b = Unit(unit_id="unit-same-b", unit_type="infantry", owner_faction_id=faction.id, movement=2, guild_id=TEST_GUILD_ID)
    await unit_a.upsert(db_conn)
    await unit_b.upsert(db_conn)
    unit_a = await Unit.fetch_by_unit_id(db_conn, "unit-same-a", TEST_GUILD_ID)
    unit_b = await Unit.fetch_by_unit_id(db_conn, "unit-same-b", TEST_GUILD_ID)

    # Check hostility
    is_hostile, reason = await are_unit_groups_hostile(
        db_conn, [unit_a], [unit_b], "T-SAME", "transit", "transit", TEST_GUILD_ID
    )
    assert is_hostile is False
    assert reason is None


@pytest.mark.asyncio
async def test_are_unit_groups_hostile_raid_vs_controller(db_conn, test_server):
    """Test that raiding units are hostile to territory controller."""
    # Create two factions (not at war)
    faction_raider = Faction(faction_id="raider-faction", name="Raider", guild_id=TEST_GUILD_ID)
    faction_defender = Faction(faction_id="defender-faction", name="Defender", guild_id=TEST_GUILD_ID)
    await faction_raider.upsert(db_conn)
    await faction_defender.upsert(db_conn)
    faction_raider = await Faction.fetch_by_faction_id(db_conn, "raider-faction", TEST_GUILD_ID)
    faction_defender = await Faction.fetch_by_faction_id(db_conn, "defender-faction", TEST_GUILD_ID)

    # Create territory controlled by defender
    territory = Territory(
        territory_id="T-RAID", name="Raid Territory", terrain_type="plains",
        controller_faction_id=faction_defender.id, guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create units
    unit_raider = Unit(unit_id="unit-raider", unit_type="infantry", owner_faction_id=faction_raider.id, movement=2, guild_id=TEST_GUILD_ID)
    unit_defender = Unit(unit_id="unit-defender", unit_type="infantry", owner_faction_id=faction_defender.id, movement=2, guild_id=TEST_GUILD_ID)
    await unit_raider.upsert(db_conn)
    await unit_defender.upsert(db_conn)
    unit_raider = await Unit.fetch_by_unit_id(db_conn, "unit-raider", TEST_GUILD_ID)
    unit_defender = await Unit.fetch_by_unit_id(db_conn, "unit-defender", TEST_GUILD_ID)

    # Check hostility when raider is raiding
    is_hostile, reason = await are_unit_groups_hostile(
        db_conn, [unit_raider], [unit_defender], "T-RAID", "raid", None, TEST_GUILD_ID
    )
    assert is_hostile is True
    assert reason == "raid_defense"


@pytest.mark.asyncio
async def test_engagement_detection_two_hostile_moving_groups(db_conn, test_server):
    """Test that two hostile moving groups become engaged when they meet."""
    # Setup: Create two factions at war
    faction_a = Faction(faction_id="engage-faction-a", name="Engage A", guild_id=TEST_GUILD_ID)
    faction_b = Faction(faction_id="engage-faction-b", name="Engage B", guild_id=TEST_GUILD_ID)
    await faction_a.upsert(db_conn)
    await faction_b.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, "engage-faction-a", TEST_GUILD_ID)
    faction_b = await Faction.fetch_by_faction_id(db_conn, "engage-faction-b", TEST_GUILD_ID)

    # Create war
    war = War(war_id="WAR-ENGAGE-01", objective="Engagement Test", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war.upsert(db_conn)
    war = await War.fetch_by_id(db_conn, "WAR-ENGAGE-01", TEST_GUILD_ID)

    await WarParticipant(war_id=war.id, faction_id=faction_a.id, side="SIDE_A", joined_turn=1, guild_id=TEST_GUILD_ID).insert(db_conn)
    await WarParticipant(war_id=war.id, faction_id=faction_b.id, side="SIDE_B", joined_turn=1, guild_id=TEST_GUILD_ID).insert(db_conn)

    # Create characters for unit ownership
    char_a = Character(identifier="engage-char-a", name="Engage Char A", channel_id=999000000000000102, represented_faction_id=faction_a.id, guild_id=TEST_GUILD_ID)
    char_b = Character(identifier="engage-char-b", name="Engage Char B", channel_id=999000000000000103, represented_faction_id=faction_b.id, guild_id=TEST_GUILD_ID)
    await char_a.upsert(db_conn)
    await char_b.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "engage-char-a", TEST_GUILD_ID)
    char_b = await Character.fetch_by_identifier(db_conn, "engage-char-b", TEST_GUILD_ID)

    # Create territories
    t1 = Territory(territory_id="ENG1", name="Engage 1", terrain_type="plains", guild_id=TEST_GUILD_ID)
    t2 = Territory(territory_id="ENG2", name="Engage 2", terrain_type="plains", guild_id=TEST_GUILD_ID)
    t3 = Territory(territory_id="ENG3", name="Engage 3", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    await t2.upsert(db_conn)
    await t3.upsert(db_conn)

    # Create units starting from opposite ends
    unit_a = Unit(
        unit_id="unit-engage-a", name="Unit A", unit_type="infantry",
        owner_character_id=char_a.id, movement=2, organization=10, max_organization=10,
        current_territory_id="ENG1", is_naval=False, guild_id=TEST_GUILD_ID
    )
    unit_b = Unit(
        unit_id="unit-engage-b", name="Unit B", unit_type="infantry",
        owner_character_id=char_b.id, movement=2, organization=10, max_organization=10,
        current_territory_id="ENG3", is_naval=False, guild_id=TEST_GUILD_ID
    )
    await unit_a.upsert(db_conn)
    await unit_b.upsert(db_conn)
    unit_a = await Unit.fetch_by_unit_id(db_conn, "unit-engage-a", TEST_GUILD_ID)
    unit_b = await Unit.fetch_by_unit_id(db_conn, "unit-engage-b", TEST_GUILD_ID)

    # Create wargame config
    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Create transit orders heading toward each other (both will meet at ENG2)
    order_a = Order(
        order_id="order-engage-a", order_type=OrderType.UNIT.value,
        unit_ids=[unit_a.id], character_id=char_a.id,
        turn_number=1, phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={'action': 'transit', 'path': ['ENG1', 'ENG2', 'ENG3'], 'path_index': 0},
        submitted_at=datetime.now(), guild_id=TEST_GUILD_ID
    )
    order_b = Order(
        order_id="order-engage-b", order_type=OrderType.UNIT.value,
        unit_ids=[unit_b.id], character_id=char_b.id,
        turn_number=1, phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={'action': 'transit', 'path': ['ENG3', 'ENG2', 'ENG1'], 'path_index': 0},
        submitted_at=datetime.now(), guild_id=TEST_GUILD_ID
    )
    await order_a.upsert(db_conn)
    await order_b.upsert(db_conn)

    # Execute movement phase
    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Check that ENGAGEMENT_DETECTED events were generated
    engagement_events = [e for e in events if e.event_type == 'ENGAGEMENT_DETECTED']
    assert len(engagement_events) == 2  # One for each unit group

    # Both orders should have engaged status
    updated_order_a = await Order.fetch_by_order_id(db_conn, "order-engage-a", TEST_GUILD_ID)
    updated_order_b = await Order.fetch_by_order_id(db_conn, "order-engage-b", TEST_GUILD_ID)

    # Orders should be ONGOING (not SUCCESS since they were interrupted)
    assert updated_order_a.status == OrderStatus.ONGOING.value
    assert updated_order_b.status == OrderStatus.ONGOING.value


@pytest.mark.asyncio
async def test_engagement_moving_vs_stationary(db_conn, test_server):
    """Test that moving units become engaged with hostile stationary units."""
    # Setup: Create two factions at war
    faction_a = Faction(faction_id="stat-engage-a", name="Stat Engage A", guild_id=TEST_GUILD_ID)
    faction_b = Faction(faction_id="stat-engage-b", name="Stat Engage B", guild_id=TEST_GUILD_ID)
    await faction_a.upsert(db_conn)
    await faction_b.upsert(db_conn)
    faction_a = await Faction.fetch_by_faction_id(db_conn, "stat-engage-a", TEST_GUILD_ID)
    faction_b = await Faction.fetch_by_faction_id(db_conn, "stat-engage-b", TEST_GUILD_ID)

    # Create war
    war = War(war_id="WAR-STAT-01", objective="Stationary Test", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war.upsert(db_conn)
    war = await War.fetch_by_id(db_conn, "WAR-STAT-01", TEST_GUILD_ID)

    await WarParticipant(war_id=war.id, faction_id=faction_a.id, side="SIDE_A", joined_turn=1, guild_id=TEST_GUILD_ID).insert(db_conn)
    await WarParticipant(war_id=war.id, faction_id=faction_b.id, side="SIDE_B", joined_turn=1, guild_id=TEST_GUILD_ID).insert(db_conn)

    # Create character for moving unit
    char_a = Character(identifier="stat-char-a", name="Stat Char A", channel_id=999000000000000104, represented_faction_id=faction_a.id, guild_id=TEST_GUILD_ID)
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "stat-char-a", TEST_GUILD_ID)

    # Create territories
    t1 = Territory(territory_id="STAT1", name="Stat 1", terrain_type="plains", guild_id=TEST_GUILD_ID)
    t2 = Territory(territory_id="STAT2", name="Stat 2", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    await t2.upsert(db_conn)

    # Create moving unit (faction A)
    unit_moving = Unit(
        unit_id="unit-stat-moving", name="Moving Unit", unit_type="infantry",
        owner_character_id=char_a.id, movement=2, organization=10, max_organization=10,
        current_territory_id="STAT1", is_naval=False, guild_id=TEST_GUILD_ID
    )
    # Create stationary unit (faction B) at destination
    unit_stationary = Unit(
        unit_id="unit-stat-stationary", name="Stationary Unit", unit_type="infantry",
        owner_faction_id=faction_b.id, movement=2, organization=10, max_organization=10,
        current_territory_id="STAT2", is_naval=False, guild_id=TEST_GUILD_ID
    )
    await unit_moving.upsert(db_conn)
    await unit_stationary.upsert(db_conn)
    unit_moving = await Unit.fetch_by_unit_id(db_conn, "unit-stat-moving", TEST_GUILD_ID)
    unit_stationary = await Unit.fetch_by_unit_id(db_conn, "unit-stat-stationary", TEST_GUILD_ID)

    # Create wargame config
    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Create transit order for moving unit
    order = Order(
        order_id="order-stat-move", order_type=OrderType.UNIT.value,
        unit_ids=[unit_moving.id], character_id=char_a.id,
        turn_number=1, phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={'action': 'transit', 'path': ['STAT1', 'STAT2'], 'path_index': 0},
        submitted_at=datetime.now(), guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute movement phase
    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # Check that ENGAGEMENT_DETECTED events were generated
    engagement_events = [e for e in events if e.event_type == 'ENGAGEMENT_DETECTED']
    assert len(engagement_events) == 2  # One for moving, one for stationary

    # Both sides should be notified
    moving_event = [e for e in engagement_events if 'unit-stat-moving' in e.event_data.get('units', [])]
    stationary_event = [e for e in engagement_events if 'unit-stat-stationary' in e.event_data.get('units', [])]
    assert len(moving_event) == 1
    assert len(stationary_event) == 1


@pytest.mark.asyncio
async def test_no_engagement_friendly_units(db_conn, test_server):
    """Test that friendly units do not engage each other."""
    # Create faction
    faction = Faction(faction_id="friendly-faction", name="Friendly Faction", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "friendly-faction", TEST_GUILD_ID)

    # Create character
    char = Character(identifier="friendly-char", name="Friendly Char", channel_id=999000000000000105, represented_faction_id=faction.id, guild_id=TEST_GUILD_ID)
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "friendly-char", TEST_GUILD_ID)

    # Create territories
    t1 = Territory(territory_id="FRIEND1", name="Friend 1", terrain_type="plains", guild_id=TEST_GUILD_ID)
    t2 = Territory(territory_id="FRIEND2", name="Friend 2", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    await t2.upsert(db_conn)

    # Create moving unit
    unit_moving = Unit(
        unit_id="unit-friendly-moving", name="Moving Unit", unit_type="infantry",
        owner_character_id=char.id, movement=2, organization=10, max_organization=10,
        current_territory_id="FRIEND1", is_naval=False, guild_id=TEST_GUILD_ID
    )
    # Create stationary unit from same faction at destination
    unit_stationary = Unit(
        unit_id="unit-friendly-stationary", name="Stationary Unit", unit_type="infantry",
        owner_faction_id=faction.id, movement=2, organization=10, max_organization=10,
        current_territory_id="FRIEND2", is_naval=False, guild_id=TEST_GUILD_ID
    )
    await unit_moving.upsert(db_conn)
    await unit_stationary.upsert(db_conn)
    unit_moving = await Unit.fetch_by_unit_id(db_conn, "unit-friendly-moving", TEST_GUILD_ID)

    # Create wargame config
    config = WargameConfig(current_turn=0, guild_id=TEST_GUILD_ID)
    await config.upsert(db_conn)

    # Create transit order
    order = Order(
        order_id="order-friendly-move", order_type=OrderType.UNIT.value,
        unit_ids=[unit_moving.id], character_id=char.id,
        turn_number=1, phase=TurnPhase.MOVEMENT.value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.PENDING.value,
        order_data={'action': 'transit', 'path': ['FRIEND1', 'FRIEND2'], 'path_index': 0},
        submitted_at=datetime.now(), guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Execute movement phase
    events = await execute_movement_phase(db_conn, TEST_GUILD_ID, 1)

    # No engagement events should be generated
    engagement_events = [e for e in events if e.event_type == 'ENGAGEMENT_DETECTED']
    assert len(engagement_events) == 0

    # Order should complete successfully
    updated_order = await Order.fetch_by_order_id(db_conn, "order-friendly-move", TEST_GUILD_ID)
    assert updated_order.status == OrderStatus.SUCCESS.value


# ============================================================================
# Event Formatting Tests for Engagement
# ============================================================================

def test_engagement_detected_character_line_format():
    """Test ENGAGEMENT_DETECTED character line formatting."""
    event_data = {
        'units': ['unit-1', 'unit-2'],
        'territory': 'T5',
        'engaged_with': ['enemy-1'],
        'reason': 'war',
        'affected_character_ids': [123]
    }
    line = engagement_detected_character_line(event_data)
    assert 'unit-1' in line
    assert 'unit-2' in line
    assert 'T5' in line
    assert 'enemy-1' in line
    assert 'war' in line


def test_engagement_detected_gm_line_format():
    """Test ENGAGEMENT_DETECTED GM line formatting."""
    event_data = {
        'units': ['unit-1'],
        'territory': 'T5',
        'engaged_with': ['enemy-1'],
        'reason': 'raid_defense',
        'affected_character_ids': [123]
    }
    line = engagement_detected_gm_line(event_data)
    assert 'unit-1' in line
    assert 'T5' in line
    assert 'enemy-1' in line
    assert 'raid_defense' in line
