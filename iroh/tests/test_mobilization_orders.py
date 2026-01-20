"""
Tests for mobilization order submission and execution.
"""
import pytest
from datetime import datetime

from db import (
    Character, Faction, FactionMember, Territory, Unit, UnitType,
    Order, TurnLog, PlayerResources, FactionResources, FactionPermission,
    Alliance
)
from handlers.order_handlers import submit_mobilization_order
from orders.construction_orders import handle_mobilization_order, generate_unit_id
from order_types import OrderType, OrderStatus, TurnPhase

TEST_GUILD_ID = 999999999999999999


@pytest.fixture
async def mobilization_setup(db_conn, test_server):
    """Set up test data for mobilization tests."""
    # Create characters
    char_leader = Character(
        identifier="mob-leader", name="Mobilization Leader",
        user_id=100000000000000301, channel_id=900000000000000301,
        guild_id=TEST_GUILD_ID
    )
    await char_leader.upsert(db_conn)
    char_leader = await Character.fetch_by_identifier(db_conn, "mob-leader", TEST_GUILD_ID)

    char_member = Character(
        identifier="mob-member", name="Mobilization Member",
        user_id=100000000000000302, channel_id=900000000000000302,
        guild_id=TEST_GUILD_ID
    )
    await char_member.upsert(db_conn)
    char_member = await Character.fetch_by_identifier(db_conn, "mob-member", TEST_GUILD_ID)

    # Create faction with nation
    faction = Faction(
        faction_id="mob-faction",
        name="Mobilization Faction",
        leader_character_id=char_leader.id,
        nation="fire-nation",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "mob-faction", TEST_GUILD_ID)

    # Add members
    member1 = FactionMember(
        character_id=char_leader.id,
        faction_id=faction.id,
        joined_turn=0,
        guild_id=TEST_GUILD_ID
    )
    await member1.insert(db_conn)

    member2 = FactionMember(
        character_id=char_member.id,
        faction_id=faction.id,
        joined_turn=0,
        guild_id=TEST_GUILD_ID
    )
    await member2.insert(db_conn)

    # Create territory with matching original_nation
    territory = Territory(
        territory_id="mob-territory-1",
        name="Fire Territory",
        terrain_type="plains",
        original_nation="fire-nation",
        controller_faction_id=faction.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create unit type with nation
    unit_type = UnitType(
        type_id="mob-infantry",
        name="Mobilization Infantry",
        nation="fire-nation",
        movement=2,
        organization=10,
        attack=5,
        defense=5,
        cost_ore=5,
        cost_lumber=2,
        cost_rations=10,
        cost_cloth=5,
        upkeep_rations=2,
        guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    # Give leader resources
    resources = PlayerResources(
        character_id=char_leader.id,
        ore=100, lumber=100, coal=100, rations=100, cloth=100, platinum=100,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    yield {
        'leader': char_leader,
        'member': char_member,
        'faction': faction,
        'territory': territory,
        'unit_type': unit_type
    }

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionResources WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionPermission WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameOrder WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


# =============================================================================
# Submission Tests
# =============================================================================


@pytest.mark.asyncio
async def test_submit_mobilization_order_personal_success(db_conn, mobilization_setup):
    """Test submitting a personal mobilization order."""
    setup = mobilization_setup

    success, message = await submit_mobilization_order(
        db_conn,
        unit_type_id="mob-infantry",
        territory_id="mob-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id
    )

    assert success is True
    assert "Mobilization order submitted" in message
    assert "mob-infantry" in message.lower() or "Mobilization Infantry" in message


@pytest.mark.asyncio
async def test_submit_mobilization_order_faction_success(db_conn, mobilization_setup):
    """Test submitting a faction mobilization order with CONSTRUCTION permission."""
    setup = mobilization_setup

    # Grant CONSTRUCTION permission
    perm = FactionPermission(
        faction_id=setup['faction'].id,
        character_id=setup['leader'].id,
        permission_type="CONSTRUCTION",
        guild_id=TEST_GUILD_ID
    )
    await perm.upsert(db_conn)

    # Give faction resources
    faction_resources = FactionResources(
        faction_id=setup['faction'].id,
        ore=100, lumber=100, coal=100, rations=100, cloth=100, platinum=100,
        guild_id=TEST_GUILD_ID
    )
    await faction_resources.upsert(db_conn)

    success, message = await submit_mobilization_order(
        db_conn,
        unit_type_id="mob-infantry",
        territory_id="mob-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id,
        faction_id="mob-faction"
    )

    assert success is True
    assert "Mobilization order submitted" in message
    assert "Mobilization Faction" in message


@pytest.mark.asyncio
async def test_submit_mobilization_order_no_construction_permission_fails(db_conn, mobilization_setup):
    """Test that faction mobilization fails without CONSTRUCTION permission."""
    setup = mobilization_setup

    success, message = await submit_mobilization_order(
        db_conn,
        unit_type_id="mob-infantry",
        territory_id="mob-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id,
        faction_id="mob-faction"
    )

    assert success is False
    assert "CONSTRUCTION permission" in message


@pytest.mark.asyncio
async def test_submit_mobilization_order_wrong_territory_controller_fails(db_conn, mobilization_setup):
    """Test that faction mobilization fails when faction doesn't control territory."""
    setup = mobilization_setup

    # Grant permission
    perm = FactionPermission(
        faction_id=setup['faction'].id,
        character_id=setup['leader'].id,
        permission_type="CONSTRUCTION",
        guild_id=TEST_GUILD_ID
    )
    await perm.upsert(db_conn)

    # Create territory controlled by someone else
    other_territory = Territory(
        territory_id="other-territory",
        name="Other Territory",
        terrain_type="plains",
        original_nation="fire-nation",
        controller_faction_id=None,  # Not controlled by our faction
        guild_id=TEST_GUILD_ID
    )
    await other_territory.upsert(db_conn)

    success, message = await submit_mobilization_order(
        db_conn,
        unit_type_id="mob-infantry",
        territory_id="other-territory",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id,
        faction_id="mob-faction"
    )

    assert success is False
    assert "not controlled" in message.lower()


@pytest.mark.asyncio
async def test_submit_mobilization_order_nation_mismatch_fails(db_conn, mobilization_setup):
    """Test that mobilization fails when unit nation doesn't match faction nation."""
    setup = mobilization_setup

    # Create unit type with different nation
    wrong_nation_unit = UnitType(
        type_id="earth-infantry",
        name="Earth Infantry",
        nation="earth-kingdom",  # Different from faction's fire-nation
        movement=2,
        organization=10,
        attack=5,
        defense=5,
        guild_id=TEST_GUILD_ID
    )
    await wrong_nation_unit.upsert(db_conn)

    success, message = await submit_mobilization_order(
        db_conn,
        unit_type_id="earth-infantry",
        territory_id="mob-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id
    )

    assert success is False
    assert "nation" in message.lower()


@pytest.mark.asyncio
async def test_submit_mobilization_order_territory_nation_mismatch_fails(db_conn, mobilization_setup):
    """Test that mobilization fails when territory original_nation doesn't match unit nation."""
    setup = mobilization_setup

    # Create territory with different original_nation
    wrong_nation_territory = Territory(
        territory_id="earth-territory",
        name="Earth Territory",
        terrain_type="plains",
        original_nation="earth-kingdom",  # Different from unit's fire-nation
        controller_faction_id=setup['faction'].id,
        guild_id=TEST_GUILD_ID
    )
    await wrong_nation_territory.upsert(db_conn)

    # Grant permission for faction mobilization
    perm = FactionPermission(
        faction_id=setup['faction'].id,
        character_id=setup['leader'].id,
        permission_type="CONSTRUCTION",
        guild_id=TEST_GUILD_ID
    )
    await perm.upsert(db_conn)

    success, message = await submit_mobilization_order(
        db_conn,
        unit_type_id="mob-infantry",
        territory_id="earth-territory",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id,
        faction_id="mob-faction"
    )

    assert success is False
    assert "territory" in message.lower()


@pytest.mark.asyncio
async def test_submit_mobilization_order_fifth_nation_any_territory(db_conn, mobilization_setup):
    """Test that Fifth Nation can build Fifth Nation units in any territory they control."""
    setup = mobilization_setup

    # Create Fifth Nation faction
    fifth_faction = Faction(
        faction_id="fifth-faction",
        name="Fifth Nation",
        nation="fifth-nation",
        guild_id=TEST_GUILD_ID
    )
    await fifth_faction.upsert(db_conn)
    fifth_faction = await Faction.fetch_by_faction_id(db_conn, "fifth-faction", TEST_GUILD_ID)

    # Add leader to Fifth Nation
    fifth_member = FactionMember(
        character_id=setup['leader'].id,
        faction_id=fifth_faction.id,
        joined_turn=0,
        guild_id=TEST_GUILD_ID
    )
    # Remove from old faction first
    await db_conn.execute(
        "DELETE FROM FactionMember WHERE character_id = $1 AND guild_id = $2;",
        setup['leader'].id, TEST_GUILD_ID
    )
    await fifth_member.insert(db_conn)

    # Create Fifth Nation unit type
    fifth_unit = UnitType(
        type_id="fifth-infantry",
        name="Fifth Nation Infantry",
        nation="fifth-nation",
        movement=2,
        organization=10,
        attack=5,
        defense=5,
        guild_id=TEST_GUILD_ID
    )
    await fifth_unit.upsert(db_conn)

    # Create territory with different original_nation but controlled by Fifth Nation
    fifth_territory = Territory(
        territory_id="fifth-territory",
        name="Conquered Territory",
        terrain_type="plains",
        original_nation="earth-kingdom",  # Different nation!
        controller_faction_id=fifth_faction.id,
        guild_id=TEST_GUILD_ID
    )
    await fifth_territory.upsert(db_conn)

    # Grant CONSTRUCTION permission
    perm = FactionPermission(
        faction_id=fifth_faction.id,
        character_id=setup['leader'].id,
        permission_type="CONSTRUCTION",
        guild_id=TEST_GUILD_ID
    )
    await perm.upsert(db_conn)

    success, message = await submit_mobilization_order(
        db_conn,
        unit_type_id="fifth-infantry",
        territory_id="fifth-territory",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id,
        faction_id="fifth-faction"
    )

    # Fifth Nation exception should allow this
    assert success is True
    assert "Mobilization order submitted" in message


# =============================================================================
# Execution Tests
# =============================================================================


@pytest.mark.asyncio
async def test_execute_mobilization_order_success(db_conn, mobilization_setup):
    """Test executing a mobilization order creates a unit."""
    setup = mobilization_setup

    # Submit order
    success, message = await submit_mobilization_order(
        db_conn,
        unit_type_id="mob-infantry",
        territory_id="mob-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id
    )
    assert success is True

    # Get the order
    orders = await Order.fetch_by_character(db_conn, setup['leader'].id, TEST_GUILD_ID)
    mob_order = [o for o in orders if o.order_type == OrderType.MOBILIZATION.value][0]

    # Execute the order
    events = await handle_mobilization_order(db_conn, mob_order, TEST_GUILD_ID, 1)

    assert len(events) == 1
    assert events[0].event_type == 'UNIT_MOBILIZED'
    assert events[0].event_data['unit_type'] == 'Mobilization Infantry'
    assert events[0].event_data['territory_id'] == 'mob-territory-1'

    # Verify unit was created
    units = await Unit.fetch_all(db_conn, TEST_GUILD_ID)
    new_units = [u for u in units if u.unit_type == 'mob-infantry']
    assert len(new_units) == 1
    assert new_units[0].current_territory_id == 'mob-territory-1'
    assert new_units[0].owner_character_id == setup['leader'].id


@pytest.mark.asyncio
async def test_execute_mobilization_order_insufficient_resources(db_conn, mobilization_setup):
    """Test that mobilization fails at execution if resources are insufficient."""
    setup = mobilization_setup

    # Remove resources
    await db_conn.execute(
        "UPDATE PlayerResources SET ore = 0, lumber = 0, rations = 0, cloth = 0 WHERE character_id = $1;",
        setup['leader'].id
    )

    # Submit order (should succeed - validation happens at execution)
    success, message = await submit_mobilization_order(
        db_conn,
        unit_type_id="mob-infantry",
        territory_id="mob-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id
    )
    assert success is True

    # Get and execute the order
    orders = await Order.fetch_by_character(db_conn, setup['leader'].id, TEST_GUILD_ID)
    mob_order = [o for o in orders if o.order_type == OrderType.MOBILIZATION.value][0]

    events = await handle_mobilization_order(db_conn, mob_order, TEST_GUILD_ID, 1)

    assert len(events) == 1
    assert events[0].event_type == 'MOBILIZATION_FAILED'
    assert 'insufficient' in events[0].event_data['error'].lower()


@pytest.mark.asyncio
async def test_execute_mobilization_order_creates_unit_with_correct_stats(db_conn, mobilization_setup):
    """Test that created unit has correct stats from unit type."""
    setup = mobilization_setup

    # Submit and execute order
    success, _ = await submit_mobilization_order(
        db_conn,
        unit_type_id="mob-infantry",
        territory_id="mob-territory-1",
        guild_id=TEST_GUILD_ID,
        submitting_character_id=setup['leader'].id,
        unit_name="Test Unit Name"
    )
    assert success is True

    orders = await Order.fetch_by_character(db_conn, setup['leader'].id, TEST_GUILD_ID)
    mob_order = [o for o in orders if o.order_type == OrderType.MOBILIZATION.value][0]
    await handle_mobilization_order(db_conn, mob_order, TEST_GUILD_ID, 1)

    # Verify unit stats match unit type
    units = await Unit.fetch_all(db_conn, TEST_GUILD_ID)
    new_unit = [u for u in units if u.unit_type == 'mob-infantry'][0]

    assert new_unit.name == "Test Unit Name"
    assert new_unit.movement == 2
    assert new_unit.organization == 10
    assert new_unit.max_organization == 10
    assert new_unit.attack == 5
    assert new_unit.defense == 5
    assert new_unit.upkeep_rations == 2


# =============================================================================
# Unit ID Generation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_generate_unit_id_fire_nation(db_conn, test_server):
    """Test unit ID generation for fire-nation."""
    unit_id = await generate_unit_id(db_conn, "fire-nation", TEST_GUILD_ID)
    assert unit_id.startswith("FN-")


@pytest.mark.asyncio
async def test_generate_unit_id_earth_kingdom(db_conn, test_server):
    """Test unit ID generation for earth-kingdom."""
    unit_id = await generate_unit_id(db_conn, "earth-kingdom", TEST_GUILD_ID)
    assert unit_id.startswith("EK-")


@pytest.mark.asyncio
async def test_generate_unit_id_fifth_nation(db_conn, test_server):
    """Test unit ID generation for fifth-nation."""
    unit_id = await generate_unit_id(db_conn, "fifth-nation", TEST_GUILD_ID)
    assert unit_id.startswith("5N-")


@pytest.mark.asyncio
async def test_generate_unit_id_unknown_nation(db_conn, test_server):
    """Test unit ID generation for unknown nation uses UN prefix."""
    unit_id = await generate_unit_id(db_conn, "unknown-nation", TEST_GUILD_ID)
    assert unit_id.startswith("UN-")


@pytest.mark.asyncio
async def test_generate_unit_id_increments(db_conn, test_server):
    """Test that unit IDs increment correctly."""
    # Create a character for ownership
    char = Character(
        identifier="unit-id-test-char", name="Test Char",
        user_id=100000000000000399, channel_id=900000000000000399,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "unit-id-test-char", TEST_GUILD_ID)

    # Create a unit with FN-001
    unit = Unit(
        unit_id="FN-001",
        name="Test Unit",
        unit_type="infantry",
        owner_character_id=char.id,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Generate next ID
    unit_id = await generate_unit_id(db_conn, "fire-nation", TEST_GUILD_ID)
    assert unit_id == "FN-002"

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
