"""
Tests for unit order submission (submit_unit_order handler).
"""
import pytest
import json
from datetime import datetime
from db import Character, Territory, TerritoryAdjacency, Unit, UnitType, Order, Faction, FactionMember, FactionPermission, WargameConfig
from handlers.order_handlers import submit_unit_order, VALID_LAND_ACTIONS, VALID_NAVAL_ACTIONS, VALID_UNIT_ACTIONS
from order_types import OrderType, OrderStatus, TurnPhase

# Test guild ID from conftest
TEST_GUILD_ID = 999999999999999999


def parse_order_data(order_data):
    """Parse order_data from raw SQL (may be JSON string or dict)."""
    if isinstance(order_data, str):
        return json.loads(order_data)
    return order_data


# ============================================================
# Test helpers
# ============================================================

async def create_test_character(db_conn, identifier="test-char", name="Test Character"):
    """Create and return a test character."""
    char = Character(
        identifier=identifier, name=name,
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    return await Character.fetch_by_identifier(db_conn, identifier, TEST_GUILD_ID)


async def create_test_territories(db_conn, territory_ids, terrain_type="plains"):
    """Create test territories with specified IDs."""
    territories = []
    for tid in territory_ids:
        territory = Territory(
            territory_id=tid, name=f"Territory {tid}", terrain_type=terrain_type,
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)
        territories.append(territory)
    return territories


async def create_adjacencies(db_conn, pairs):
    """Create adjacencies between territory pairs."""
    for a, b in pairs:
        adjacency = TerritoryAdjacency(
            territory_a_id=a, territory_b_id=b, guild_id=TEST_GUILD_ID
        )
        await adjacency.upsert(db_conn)


async def create_test_unit(db_conn, unit_id, owner_character_id, current_territory_id, is_naval=False, movement=2):
    """Create a test unit."""
    # Create unit type if needed
    unit_type_id = "naval" if is_naval else "infantry"
    unit_type = await UnitType.fetch_by_type_id(db_conn, unit_type_id, TEST_GUILD_ID)
    if not unit_type:
        unit_type = UnitType(
            type_id=unit_type_id, name="Naval" if is_naval else "Infantry", nation="test",
            movement=movement, organization=100, attack=5, defense=5,
            siege_attack=0, siege_defense=0, is_naval=is_naval, guild_id=TEST_GUILD_ID
        )
        await unit_type.upsert(db_conn)

    unit = Unit(
        unit_id=unit_id, unit_type=unit_type_id,
        owner_character_id=owner_character_id, movement=movement,
        organization=100, max_organization=100,
        current_territory_id=current_territory_id, is_naval=is_naval,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    return await Unit.fetch_by_unit_id(db_conn, unit_id, TEST_GUILD_ID)


async def create_wargame_config(db_conn, current_turn=5):
    """Create WargameConfig."""
    config = WargameConfig(guild_id=TEST_GUILD_ID, current_turn=current_turn)
    await config.upsert(db_conn)


async def cleanup_orders(db_conn):
    """Clean up orders."""
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)


async def full_cleanup(db_conn):
    """Full cleanup of test data."""
    await db_conn.execute('DELETE FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionPermission WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


# ============================================================
# Submission tests - Each action type submits successfully
# ============================================================

@pytest.mark.asyncio
async def test_submit_unit_order_transit(db_conn, test_server):
    """Test submitting a transit unit order."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102"])
    await create_adjacencies(db_conn, [("101", "102")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "transit", ["101", "102"], TEST_GUILD_ID, char.id
    )

    assert success is True
    assert "unit order submitted" in message.lower()
    assert "transit" in message.lower()
    assert "TEST-001" in message

    # Verify order was created
    orders = await db_conn.fetch('SELECT * FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    assert len(orders) == 1
    assert orders[0]['order_type'] == OrderType.UNIT.value
    order_data = parse_order_data(orders[0]['order_data'])
    assert order_data['action'] == 'transit'

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_submit_unit_order_patrol_with_speed(db_conn, test_server):
    """Test submitting a patrol order with speed parameter."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102", "103"])
    await create_adjacencies(db_conn, [("101", "102"), ("102", "103")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "patrol", ["101", "102", "103"], TEST_GUILD_ID, char.id, speed=2
    )

    assert success is True
    assert "patrol" in message.lower()

    # Verify order has speed in order_data
    orders = await db_conn.fetch('SELECT * FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    order_data = parse_order_data(orders[0]['order_data'])
    assert order_data['speed'] == 2

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_submit_unit_order_raid(db_conn, test_server):
    """Test submitting a raid order."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102"])
    await create_adjacencies(db_conn, [("101", "102")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "raid", ["101", "102"], TEST_GUILD_ID, char.id
    )

    assert success is True
    assert "raid" in message.lower()

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_submit_unit_order_capture(db_conn, test_server):
    """Test submitting a capture order."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102"])
    await create_adjacencies(db_conn, [("101", "102")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "capture", ["101", "102"], TEST_GUILD_ID, char.id
    )

    assert success is True
    assert "capture" in message.lower()

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_submit_unit_order_transport(db_conn, test_server):
    """Test submitting a transport order."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102"])
    await create_adjacencies(db_conn, [("101", "102")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "transport", ["101", "102"], TEST_GUILD_ID, char.id
    )

    assert success is True
    assert "transport" in message.lower()

    await full_cleanup(db_conn)


# ============================================================
# Naval action tests
# ============================================================

@pytest.mark.asyncio
async def test_submit_unit_order_naval_transit(db_conn, test_server):
    """Test submitting a naval transit order."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["W01", "W02"], terrain_type="ocean")
    await create_adjacencies(db_conn, [("W01", "W02")])
    await create_test_unit(db_conn, "SHIP-001", char.id, "W01", is_naval=True)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["SHIP-001"], "naval_transit", ["W01", "W02"], TEST_GUILD_ID, char.id
    )

    assert success is True
    assert "naval_transit" in message.lower()

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_submit_unit_order_naval_patrol_with_speed(db_conn, test_server):
    """Test submitting a naval patrol order with speed."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["W01", "W02", "W03"], terrain_type="ocean")
    await create_adjacencies(db_conn, [("W01", "W02"), ("W02", "W03")])
    await create_test_unit(db_conn, "SHIP-001", char.id, "W01", is_naval=True)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["SHIP-001"], "naval_patrol", ["W01", "W02", "W03"], TEST_GUILD_ID, char.id, speed=3
    )

    assert success is True
    assert "naval_patrol" in message.lower()

    orders = await db_conn.fetch('SELECT * FROM WargameOrder WHERE guild_id = $1;', TEST_GUILD_ID)
    order_data = parse_order_data(orders[0]['order_data'])
    assert order_data['speed'] == 3

    await full_cleanup(db_conn)


# ============================================================
# Land vs Naval validation
# ============================================================

@pytest.mark.asyncio
async def test_land_action_fails_for_naval_unit(db_conn, test_server):
    """Test that land actions fail for naval units."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["W01", "W02"], terrain_type="ocean")
    await create_adjacencies(db_conn, [("W01", "W02")])
    await create_test_unit(db_conn, "SHIP-001", char.id, "W01", is_naval=True)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["SHIP-001"], "transit", ["W01", "W02"], TEST_GUILD_ID, char.id
    )

    assert success is False
    assert "naval unit" in message.lower()
    assert "land action" in message.lower()

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_naval_action_fails_for_land_unit(db_conn, test_server):
    """Test that naval actions fail for land units."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102"])
    await create_adjacencies(db_conn, [("101", "102")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "naval_transit", ["101", "102"], TEST_GUILD_ID, char.id
    )

    assert success is False
    assert "land unit" in message.lower()
    assert "naval action" in message.lower()

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_naval_unit_cannot_traverse_land(db_conn, test_server):
    """Test that naval units cannot traverse land terrain."""
    char = await create_test_character(db_conn)
    # Mix of water and land territories
    t1 = Territory(territory_id="W01", name="Ocean 1", terrain_type="ocean", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    t2 = Territory(territory_id="L01", name="Land 1", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t2.upsert(db_conn)
    await create_adjacencies(db_conn, [("W01", "L01")])
    await create_test_unit(db_conn, "SHIP-001", char.id, "W01", is_naval=True)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["SHIP-001"], "naval_transit", ["W01", "L01"], TEST_GUILD_ID, char.id
    )

    assert success is False
    assert "land territory" in message.lower() or "terrain" in message.lower()

    await full_cleanup(db_conn)


# ============================================================
# Authorization tests
# ============================================================

@pytest.mark.asyncio
async def test_owner_can_issue_order(db_conn, test_server):
    """Test that unit owner can issue orders."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102"])
    await create_adjacencies(db_conn, [("101", "102")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "transit", ["101", "102"], TEST_GUILD_ID, char.id
    )

    assert success is True

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_non_owner_cannot_issue_order(db_conn, test_server):
    """Test that non-owner cannot issue orders for character-owned unit."""
    owner = await create_test_character(db_conn, "owner", "Owner")
    other = await create_test_character(db_conn, "other", "Other Person")
    await create_test_territories(db_conn, ["101", "102"])
    await create_adjacencies(db_conn, [("101", "102")])
    await create_test_unit(db_conn, "TEST-001", owner.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "transit", ["101", "102"], TEST_GUILD_ID, other.id
    )

    assert success is False
    assert "not authorized" in message.lower()

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_commander_can_issue_order(db_conn, test_server):
    """Test that unit commander can issue orders."""
    owner = await create_test_character(db_conn, "owner", "Owner")
    commander = await create_test_character(db_conn, "commander", "Commander")
    await create_test_territories(db_conn, ["101", "102"])
    await create_adjacencies(db_conn, [("101", "102")])

    # Create unit with commander
    unit = Unit(
        unit_id="TEST-001", unit_type="infantry",
        owner_character_id=owner.id,
        commander_character_id=commander.id,
        movement=2, organization=100, max_organization=100,
        current_territory_id="101", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry", nation="test",
        movement=2, organization=100, attack=5, defense=5,
        siege_attack=0, siege_defense=0, guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    await create_wargame_config(db_conn)

    # Commander should be able to issue order
    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "transit", ["101", "102"], TEST_GUILD_ID, commander.id
    )

    assert success is True

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_faction_command_permission(db_conn, test_server):
    """Test that character with COMMAND permission can issue orders for faction units."""
    leader = await create_test_character(db_conn, "leader", "Leader")
    member = await create_test_character(db_conn, "member", "Member with Permission")

    # Create faction
    faction = Faction(
        faction_id="TEST-FACTION", name="Test Faction",
        leader_character_id=leader.id, guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "TEST-FACTION", TEST_GUILD_ID)

    # Add member to faction
    membership = FactionMember(
        faction_id=faction.id, character_id=member.id, guild_id=TEST_GUILD_ID
    )
    await membership.upsert(db_conn)

    # Grant COMMAND permission
    permission = FactionPermission(
        faction_id=faction.id, character_id=member.id,
        permission_type="COMMAND", guild_id=TEST_GUILD_ID
    )
    await permission.upsert(db_conn)

    await create_test_territories(db_conn, ["101", "102"])
    await create_adjacencies(db_conn, [("101", "102")])

    # Create faction-owned unit
    unit_type = UnitType(
        type_id="infantry", name="Infantry", nation="test",
        movement=2, organization=100, attack=5, defense=5,
        siege_attack=0, siege_defense=0, guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    unit = Unit(
        unit_id="FACTION-001", unit_type="infantry",
        owner_faction_id=faction.id,
        movement=2, organization=100, max_organization=100,
        current_territory_id="101", is_naval=False,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    await create_wargame_config(db_conn)

    # Member with COMMAND permission should succeed
    success, message, extra = await submit_unit_order(
        db_conn, ["FACTION-001"], "transit", ["101", "102"], TEST_GUILD_ID, member.id
    )

    assert success is True

    await full_cleanup(db_conn)


# ============================================================
# Path validation tests
# ============================================================

@pytest.mark.asyncio
async def test_path_must_start_at_current_territory(db_conn, test_server):
    """Test that path must start at unit's current territory."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102", "103"])
    await create_adjacencies(db_conn, [("101", "102"), ("102", "103")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    # Path starts at 102, but unit is at 101
    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "transit", ["102", "103"], TEST_GUILD_ID, char.id
    )

    assert success is False
    assert "must start" in message.lower() or "current territory" in message.lower()

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_non_adjacent_territories_fail(db_conn, test_server):
    """Test that non-adjacent territories are identified in error message."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102", "103"])
    # Only 101-102 are adjacent, not 102-103
    await create_adjacencies(db_conn, [("101", "102")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "transit", ["101", "102", "103"], TEST_GUILD_ID, char.id
    )

    assert success is False
    assert "not adjacent" in message.lower()
    assert "102" in message and "103" in message

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_nonexistent_territory_fails(db_conn, test_server):
    """Test that nonexistent territory in path fails."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101"])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "transit", ["101", "999"], TEST_GUILD_ID, char.id
    )

    assert success is False
    assert "not found" in message.lower()
    assert "999" in message

    await full_cleanup(db_conn)


# ============================================================
# Confirmation flow tests
# ============================================================

@pytest.mark.asyncio
async def test_existing_orders_trigger_confirmation(db_conn, test_server):
    """Test that existing orders trigger confirmation_needed."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102", "103"])
    await create_adjacencies(db_conn, [("101", "102"), ("102", "103")])
    unit = await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    # Submit first order
    success1, message1, extra1 = await submit_unit_order(
        db_conn, ["TEST-001"], "transit", ["101", "102"], TEST_GUILD_ID, char.id
    )
    assert success1 is True

    # Try to submit second order without override
    success2, message2, extra2 = await submit_unit_order(
        db_conn, ["TEST-001"], "transit", ["101", "102", "103"], TEST_GUILD_ID, char.id
    )

    assert success2 is False
    assert extra2 is not None
    assert extra2.get('confirmation_needed') is True
    assert 'existing_orders' in extra2
    assert len(extra2['existing_orders']) == 1

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_override_cancels_existing_and_creates_new(db_conn, test_server):
    """Test that override=True cancels existing orders and creates new one."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102", "103"])
    await create_adjacencies(db_conn, [("101", "102"), ("102", "103")])
    unit = await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    # Submit first order
    success1, message1, extra1 = await submit_unit_order(
        db_conn, ["TEST-001"], "transit", ["101", "102"], TEST_GUILD_ID, char.id
    )
    assert success1 is True

    # Get first order
    orders_before = await db_conn.fetch('SELECT * FROM WargameOrder WHERE guild_id = $1 AND status = $2;', TEST_GUILD_ID, OrderStatus.PENDING.value)
    assert len(orders_before) == 1
    first_order_id = orders_before[0]['order_id']

    # Submit second order with override
    success2, message2, extra2 = await submit_unit_order(
        db_conn, ["TEST-001"], "raid", ["101", "102", "103"], TEST_GUILD_ID, char.id, override=True
    )

    assert success2 is True
    assert "previous orders cancelled" in message2.lower()

    # Check first order is cancelled
    first_order = await db_conn.fetchrow('SELECT * FROM WargameOrder WHERE order_id = $1 AND guild_id = $2;', first_order_id, TEST_GUILD_ID)
    assert first_order['status'] == OrderStatus.CANCELLED.value

    # Check new order exists
    new_orders = await db_conn.fetch('SELECT * FROM WargameOrder WHERE guild_id = $1 AND status = $2;', TEST_GUILD_ID, OrderStatus.PENDING.value)
    assert len(new_orders) == 1
    new_order_data = parse_order_data(new_orders[0]['order_data'])
    assert new_order_data['action'] == 'raid'

    await full_cleanup(db_conn)


# ============================================================
# Action-specific tests
# ============================================================

@pytest.mark.asyncio
async def test_siege_requires_city_terrain(db_conn, test_server):
    """Test that siege action requires city terrain at destination."""
    char = await create_test_character(db_conn)
    t1 = Territory(territory_id="101", name="Plains", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    t2 = Territory(territory_id="102", name="Also Plains", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t2.upsert(db_conn)
    await create_adjacencies(db_conn, [("101", "102")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "siege", ["101", "102"], TEST_GUILD_ID, char.id
    )

    assert success is False
    assert "city" in message.lower()

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_siege_succeeds_with_city_terrain(db_conn, test_server):
    """Test that siege action succeeds with city terrain at destination."""
    char = await create_test_character(db_conn)
    t1 = Territory(territory_id="101", name="Plains", terrain_type="plains", guild_id=TEST_GUILD_ID)
    await t1.upsert(db_conn)
    t2 = Territory(territory_id="102", name="City", terrain_type="city", guild_id=TEST_GUILD_ID)
    await t2.upsert(db_conn)
    await create_adjacencies(db_conn, [("101", "102")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "siege", ["101", "102"], TEST_GUILD_ID, char.id
    )

    assert success is True
    assert "siege" in message.lower()

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_speed_only_valid_for_patrol(db_conn, test_server):
    """Test that speed parameter is only valid for patrol actions."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102"])
    await create_adjacencies(db_conn, [("101", "102")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    # Speed with transit should fail
    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "transit", ["101", "102"], TEST_GUILD_ID, char.id, speed=2
    )

    assert success is False
    assert "speed" in message.lower()
    assert "patrol" in message.lower()

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_patrol_requires_two_different_territories(db_conn, test_server):
    """Test that patrol path must contain at least two different territories."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102"])
    await create_adjacencies(db_conn, [("101", "102")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    # Patrol with only one unique territory (start and end same) should fail
    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "patrol", ["101", "101"], TEST_GUILD_ID, char.id
    )

    assert success is False
    assert "two different territories" in message.lower()

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_patrol_with_two_different_territories_succeeds(db_conn, test_server):
    """Test that patrol path with two different territories succeeds."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102"])
    await create_adjacencies(db_conn, [("101", "102")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    # Patrol with two different territories should succeed
    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "patrol", ["101", "102"], TEST_GUILD_ID, char.id
    )

    assert success is True

    await full_cleanup(db_conn)


# ============================================================
# Invalid action tests
# ============================================================

@pytest.mark.asyncio
async def test_invalid_action_fails(db_conn, test_server):
    """Test that invalid action type fails."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102"])
    await create_adjacencies(db_conn, [("101", "102")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001"], "invalid_action", ["101", "102"], TEST_GUILD_ID, char.id
    )

    assert success is False
    assert "invalid action" in message.lower()

    await full_cleanup(db_conn)


# ============================================================
# Unit group tests
# ============================================================

@pytest.mark.asyncio
async def test_multiple_units_same_territory(db_conn, test_server):
    """Test submitting order for multiple units in same territory."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102"])
    await create_adjacencies(db_conn, [("101", "102")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_test_unit(db_conn, "TEST-002", char.id, "101", is_naval=False)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001", "TEST-002"], "transit", ["101", "102"], TEST_GUILD_ID, char.id
    )

    assert success is True
    assert "TEST-001" in message
    assert "TEST-002" in message

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_multiple_units_different_territories_fail(db_conn, test_server):
    """Test that multiple units in different territories fail."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102", "103"])
    await create_adjacencies(db_conn, [("101", "102"), ("102", "103")])
    await create_test_unit(db_conn, "TEST-001", char.id, "101", is_naval=False)
    await create_test_unit(db_conn, "TEST-002", char.id, "102", is_naval=False)
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["TEST-001", "TEST-002"], "transit", ["101", "102"], TEST_GUILD_ID, char.id
    )

    assert success is False
    assert "same territory" in message.lower()

    await full_cleanup(db_conn)


@pytest.mark.asyncio
async def test_nonexistent_unit_fails(db_conn, test_server):
    """Test that nonexistent unit fails."""
    char = await create_test_character(db_conn)
    await create_test_territories(db_conn, ["101", "102"])
    await create_adjacencies(db_conn, [("101", "102")])
    await create_wargame_config(db_conn)

    success, message, extra = await submit_unit_order(
        db_conn, ["NONEXISTENT-001"], "transit", ["101", "102"], TEST_GUILD_ID, char.id
    )

    assert success is False
    assert "not found" in message.lower()

    await full_cleanup(db_conn)
