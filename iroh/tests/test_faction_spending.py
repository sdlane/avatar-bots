"""
Pytest tests for faction spending during the upkeep phase.
Tests verify spending deduction, partial spending, and event generation.

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_faction_spending.py -v
"""
import pytest
from handlers.turn_handlers import execute_upkeep_phase, execute_faction_spending
from handlers.faction_handlers import edit_faction_spending, get_faction_spending
from db import Character, Faction, FactionMember, FactionResources, FactionPermission, Unit
from tests.conftest import TEST_GUILD_ID
from event_logging.upkeep_events import (
    faction_spending_character_line,
    faction_spending_gm_line,
    faction_spending_partial_character_line,
    faction_spending_partial_gm_line,
)


@pytest.mark.asyncio
async def test_faction_spending_full_payment(db_conn, test_server):
    """Test faction spending is fully deducted when faction has sufficient resources."""
    # Create faction with spending
    faction = Faction(
        faction_id="spending-faction",
        name="Spending Faction",
        guild_id=TEST_GUILD_ID,
        ore_spending=10,
        lumber_spending=5,
        coal_spending=0,
        rations_spending=20,
        cloth_spending=0,
        platinum_spending=0
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "spending-faction", TEST_GUILD_ID)

    # Create faction resources (more than enough)
    resources = FactionResources(
        faction_id=faction.id,
        ore=100, lumber=50, coal=30, rations=200, cloth=20, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute faction spending
    events = await execute_faction_spending(db_conn, TEST_GUILD_ID, 1)

    # Verify FACTION_SPENDING event generated
    assert len(events) == 1
    event = events[0]
    assert event.phase == 'UPKEEP'
    assert event.event_type == 'FACTION_SPENDING'
    assert event.entity_type == 'faction'
    assert event.entity_id == faction.id
    assert event.event_data['faction_name'] == 'Spending Faction'
    assert event.event_data['amounts_spent']['ore'] == 10
    assert event.event_data['amounts_spent']['lumber'] == 5
    assert event.event_data['amounts_spent']['rations'] == 20
    assert 'coal' not in event.event_data['amounts_spent']  # Zero spending not included

    # Verify resources were deducted
    updated_resources = await FactionResources.fetch_by_faction(db_conn, faction.id, TEST_GUILD_ID)
    assert updated_resources.ore == 90  # 100 - 10
    assert updated_resources.lumber == 45  # 50 - 5
    assert updated_resources.coal == 30  # unchanged
    assert updated_resources.rations == 180  # 200 - 20


@pytest.mark.asyncio
async def test_faction_spending_partial_payment(db_conn, test_server):
    """Test partial spending when faction lacks some resources."""
    # Create faction with spending
    faction = Faction(
        faction_id="partial-faction",
        name="Partial Faction",
        guild_id=TEST_GUILD_ID,
        ore_spending=50,
        lumber_spending=30,
        coal_spending=0,
        rations_spending=0,
        cloth_spending=0,
        platinum_spending=0
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "partial-faction", TEST_GUILD_ID)

    # Create faction resources (insufficient for full spending)
    resources = FactionResources(
        faction_id=faction.id,
        ore=30, lumber=50, coal=0, rations=0, cloth=0, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute faction spending
    events = await execute_faction_spending(db_conn, TEST_GUILD_ID, 1)

    # Verify both FACTION_SPENDING and FACTION_SPENDING_PARTIAL events
    assert len(events) == 2

    spending_event = next(e for e in events if e.event_type == 'FACTION_SPENDING')
    assert spending_event.event_data['amounts_spent']['ore'] == 30  # Only had 30
    assert spending_event.event_data['amounts_spent']['lumber'] == 30

    partial_event = next(e for e in events if e.event_type == 'FACTION_SPENDING_PARTIAL')
    assert partial_event.event_data['shortfall']['ore'] == 20  # Needed 50, had 30

    # Verify resources depleted
    updated_resources = await FactionResources.fetch_by_faction(db_conn, faction.id, TEST_GUILD_ID)
    assert updated_resources.ore == 0  # 30 - 30 (spent all available)
    assert updated_resources.lumber == 20  # 50 - 30


@pytest.mark.asyncio
async def test_faction_spending_no_resources(db_conn, test_server):
    """Test spending when faction has zero resources."""
    # Create faction with spending
    faction = Faction(
        faction_id="no-resources-faction",
        name="No Resources Faction",
        guild_id=TEST_GUILD_ID,
        ore_spending=10,
        lumber_spending=10,
        coal_spending=0,
        rations_spending=0,
        cloth_spending=0,
        platinum_spending=0
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "no-resources-faction", TEST_GUILD_ID)

    # No FactionResources created - faction has no resources

    # Execute faction spending
    events = await execute_faction_spending(db_conn, TEST_GUILD_ID, 1)

    # Should only have partial event (nothing spent)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == 'FACTION_SPENDING_PARTIAL'
    assert event.event_data['shortfall']['ore'] == 10
    assert event.event_data['shortfall']['lumber'] == 10


@pytest.mark.asyncio
async def test_faction_spending_zero_spending(db_conn, test_server):
    """Test no events when faction has zero spending configured."""
    # Create faction with zero spending
    faction = Faction(
        faction_id="zero-spending-faction",
        name="Zero Spending Faction",
        guild_id=TEST_GUILD_ID,
        ore_spending=0,
        lumber_spending=0,
        coal_spending=0,
        rations_spending=0,
        cloth_spending=0,
        platinum_spending=0
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "zero-spending-faction", TEST_GUILD_ID)

    # Create faction resources
    resources = FactionResources(
        faction_id=faction.id,
        ore=100, lumber=50, coal=30, rations=200, cloth=20, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute faction spending
    events = await execute_faction_spending(db_conn, TEST_GUILD_ID, 1)

    # No events should be generated
    assert len(events) == 0

    # Resources should be unchanged
    updated_resources = await FactionResources.fetch_by_faction(db_conn, faction.id, TEST_GUILD_ID)
    assert updated_resources.ore == 100
    assert updated_resources.lumber == 50


@pytest.mark.asyncio
async def test_faction_spending_before_unit_upkeep(db_conn, test_server):
    """Test that faction spending happens before unit upkeep in the upkeep phase."""
    # Create character for unit ownership
    character = Character(
        identifier="spending-order-char", name="Spending Order Tester",
        channel_id=999000000000000001, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "spending-order-char", TEST_GUILD_ID)

    # Create faction with spending
    faction = Faction(
        faction_id="order-test-faction",
        name="Order Test Faction",
        guild_id=TEST_GUILD_ID,
        ore_spending=5,
        lumber_spending=0,
        coal_spending=0,
        rations_spending=0,
        cloth_spending=0,
        platinum_spending=0
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "order-test-faction", TEST_GUILD_ID)

    # Create faction resources
    faction_resources = FactionResources(
        faction_id=faction.id,
        ore=10, lumber=0, coal=0, rations=0, cloth=0, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await faction_resources.upsert(db_conn)

    # Create unit owned by character
    unit = Unit(
        unit_id="order-test-unit", name="Order Test Unit", unit_type="infantry",
        owner_character_id=character.id,
        organization=10, max_organization=10,
        upkeep_ore=3,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Create character resources
    char_resources = FactionResources(
        faction_id=faction.id,
        ore=5, lumber=0, coal=0, rations=0, cloth=0, platinum=0,
        guild_id=TEST_GUILD_ID
    )

    # Execute full upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # FACTION_SPENDING event should come first
    assert len(events) >= 1
    assert events[0].event_type == 'FACTION_SPENDING'


@pytest.mark.asyncio
async def test_edit_faction_spending_handler(db_conn, test_server):
    """Test the edit_faction_spending handler validates and updates spending."""
    # Create faction with initial spending
    faction = Faction(
        faction_id="edit-spending-faction",
        name="Edit Spending Faction",
        guild_id=TEST_GUILD_ID,
        ore_spending=5,
        lumber_spending=5,
        coal_spending=5,
        rations_spending=5,
        cloth_spending=5,
        platinum_spending=5
    )
    await faction.upsert(db_conn)

    # Edit only some spending values
    spending = {
        'ore': 10,
        'rations': 20,
        'platinum': 3
    }
    success, message = await edit_faction_spending(db_conn, "edit-spending-faction", TEST_GUILD_ID, spending)

    assert success is True
    assert "Updated spending" in message

    # Verify only specified spending was changed, others remain unchanged
    updated_faction = await Faction.fetch_by_faction_id(db_conn, "edit-spending-faction", TEST_GUILD_ID)
    assert updated_faction.ore_spending == 10  # Changed
    assert updated_faction.lumber_spending == 5  # Unchanged
    assert updated_faction.coal_spending == 5  # Unchanged
    assert updated_faction.rations_spending == 20  # Changed
    assert updated_faction.cloth_spending == 5  # Unchanged
    assert updated_faction.platinum_spending == 3  # Changed


@pytest.mark.asyncio
async def test_edit_faction_spending_negative_not_allowed(db_conn, test_server):
    """Test that negative spending values are rejected."""
    # Create faction
    faction = Faction(
        faction_id="negative-spending-faction",
        name="Negative Spending Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Try negative spending
    spending = {
        'ore': -5,
        'lumber': 0,
        'coal': 0,
        'rations': 0,
        'cloth': 0,
        'platinum': 0
    }
    success, message = await edit_faction_spending(db_conn, "negative-spending-faction", TEST_GUILD_ID, spending)

    assert success is False
    assert "must be >= 0" in message


@pytest.mark.asyncio
async def test_get_faction_spending_regular_member_denied(db_conn, test_server):
    """Test regular faction member cannot view spending (only leader/FINANCIAL can)."""
    # Create character
    character = Character(
        identifier="member-char", name="Member Character",
        channel_id=999000000000000001, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "member-char", TEST_GUILD_ID)

    # Create faction with spending
    faction = Faction(
        faction_id="member-view-faction",
        name="Member View Faction",
        guild_id=TEST_GUILD_ID,
        ore_spending=15,
        lumber_spending=0,
        coal_spending=0,
        rations_spending=0,
        cloth_spending=0,
        platinum_spending=0
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "member-view-faction", TEST_GUILD_ID)

    # Add character to faction
    member = FactionMember(
        faction_id=faction.id,
        character_id=character.id,
        joined_turn=0,
        guild_id=TEST_GUILD_ID
    )
    await member.insert(db_conn)

    # Regular member should NOT be able to view spending (only leader/FINANCIAL can)
    success, message, data = await get_faction_spending(
        db_conn, "member-view-faction", TEST_GUILD_ID,
        viewer_character_id=character.id, is_admin=False
    )

    assert success is False
    assert "permission" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_get_faction_spending_non_member_denied(db_conn, test_server):
    """Test non-member cannot view faction spending."""
    # Create character (not in any faction)
    character = Character(
        identifier="non-member-char", name="Non-Member Character",
        channel_id=999000000000000001, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "non-member-char", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="restricted-faction",
        name="Restricted Faction",
        guild_id=TEST_GUILD_ID,
        ore_spending=10,
        lumber_spending=0,
        coal_spending=0,
        rations_spending=0,
        cloth_spending=0,
        platinum_spending=0
    )
    await faction.upsert(db_conn)

    # Try to get spending as non-member
    success, message, data = await get_faction_spending(
        db_conn, "restricted-faction", TEST_GUILD_ID,
        viewer_character_id=character.id, is_admin=False
    )

    assert success is False
    assert "permission" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_faction_spending_event_format(db_conn, test_server):
    """Test event line formatting functions."""
    # Test FACTION_SPENDING format
    spending_event_data = {
        'faction_name': 'Test Faction',
        'amounts_spent': {'ore': 10, 'lumber': 5}
    }
    char_line = faction_spending_character_line(spending_event_data)
    assert 'Test Faction' in char_line
    assert 'ore:10' in char_line
    assert 'lumber:5' in char_line

    gm_line = faction_spending_gm_line(spending_event_data)
    assert 'Test Faction' in gm_line
    assert 'ore:10' in gm_line

    # Test FACTION_SPENDING_PARTIAL format
    partial_event_data = {
        'faction_name': 'Broke Faction',
        'shortfall': {'ore': 20, 'rations': 15}
    }
    char_partial = faction_spending_partial_character_line(partial_event_data)
    assert 'Broke Faction' in char_partial
    assert 'lacking' in char_partial
    assert '20 ore' in char_partial

    gm_partial = faction_spending_partial_gm_line(partial_event_data)
    assert 'Broke Faction' in gm_partial
    assert 'short' in gm_partial
