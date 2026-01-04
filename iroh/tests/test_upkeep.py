"""
Pytest tests for the upkeep phase in turn resolution.
Tests verify resource deduction, organization penalties, and event generation.

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_upkeep.py -v
"""
import pytest
from handlers.turn_handlers import execute_upkeep_phase
from db import Character, Unit, PlayerResources
from tests.conftest import TEST_GUILD_ID
from event_logging.upkeep_events import (
    upkeep_summary_character_line,
    upkeep_summary_gm_line,
    upkeep_total_deficit_character_line,
    upkeep_total_deficit_gm_line,
    upkeep_deficit_character_line,
    upkeep_deficit_gm_line,
)


@pytest.mark.asyncio
async def test_upkeep_fully_paid_single_unit(db_conn, test_server):
    """Test upkeep is deducted when player has sufficient resources."""
    # Create character
    character = Character(
        identifier="upkeep-char", name="Upkeep Tester",
        channel_id=999000000000000001, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "upkeep-char", TEST_GUILD_ID)

    # Create unit with upkeep costs
    unit = Unit(
        unit_id="unit-1", name="Test Unit", unit_type="infantry",
        owner_character_id=character.id,
        organization=10, max_organization=10,
        upkeep_ore=5, upkeep_lumber=3, upkeep_coal=2,
        upkeep_rations=10, upkeep_cloth=1,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Create player resources (more than enough)
    resources = PlayerResources(
        character_id=character.id,
        ore=100, lumber=50, coal=30, rations=200, cloth=20,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify UPKEEP_SUMMARY event generated
    assert len(events) == 1
    event = events[0]
    assert event.phase == 'UPKEEP'
    assert event.event_type == 'UPKEEP_SUMMARY'
    assert event.entity_type == 'character'
    assert event.entity_id == character.id
    assert 'affected_character_ids' in event.event_data
    assert event.event_data['affected_character_ids'] == [character.id]
    assert event.event_data['resources_spent']['ore'] == 5
    assert event.event_data['resources_spent']['lumber'] == 3
    assert event.event_data['resources_spent']['coal'] == 2
    assert event.event_data['resources_spent']['rations'] == 10
    assert event.event_data['resources_spent']['cloth'] == 1
    assert event.event_data['units_maintained'] == 1

    # Verify resources were deducted
    updated_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert updated_resources.ore == 95  # 100 - 5
    assert updated_resources.lumber == 47  # 50 - 3
    assert updated_resources.coal == 28  # 30 - 2
    assert updated_resources.rations == 190  # 200 - 10
    assert updated_resources.cloth == 19  # 20 - 1

    # Verify unit organization unchanged (full payment)
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-1", TEST_GUILD_ID)
    assert updated_unit.organization == 10


@pytest.mark.asyncio
async def test_upkeep_fully_paid_multiple_units(db_conn, test_server):
    """Test upkeep is aggregated across multiple units for same owner."""
    # Create character
    character = Character(
        identifier="multi-unit-char", name="Multi Unit Owner",
        channel_id=999000000000000002, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "multi-unit-char", TEST_GUILD_ID)

    # Create two units with upkeep costs
    unit1 = Unit(
        unit_id="unit-a", name="Unit A", unit_type="infantry",
        owner_character_id=character.id,
        organization=8, max_organization=10,
        upkeep_ore=5, upkeep_lumber=3, upkeep_coal=0,
        upkeep_rations=10, upkeep_cloth=2,
        guild_id=TEST_GUILD_ID
    )
    await unit1.upsert(db_conn)

    unit2 = Unit(
        unit_id="unit-b", name="Unit B", unit_type="cavalry",
        owner_character_id=character.id,
        organization=6, max_organization=8,
        upkeep_ore=3, upkeep_lumber=0, upkeep_coal=5,
        upkeep_rations=8, upkeep_cloth=1,
        guild_id=TEST_GUILD_ID
    )
    await unit2.upsert(db_conn)

    # Create player resources (enough for both units)
    resources = PlayerResources(
        character_id=character.id,
        ore=50, lumber=50, coal=50, rations=100, cloth=50,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify single UPKEEP_SUMMARY event with aggregated costs
    assert len(events) == 1
    event = events[0]
    assert event.event_type == 'UPKEEP_SUMMARY'
    assert event.event_data['resources_spent']['ore'] == 8  # 5 + 3
    assert event.event_data['resources_spent']['lumber'] == 3  # 3 + 0
    assert event.event_data['resources_spent']['coal'] == 5  # 0 + 5
    assert event.event_data['resources_spent']['rations'] == 18  # 10 + 8
    assert event.event_data['resources_spent']['cloth'] == 3  # 2 + 1
    assert event.event_data['units_maintained'] == 2

    # Verify resources were deducted
    updated_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert updated_resources.ore == 42  # 50 - 8
    assert updated_resources.lumber == 47  # 50 - 3
    assert updated_resources.coal == 45  # 50 - 5
    assert updated_resources.rations == 82  # 100 - 18
    assert updated_resources.cloth == 47  # 50 - 3

    # Verify both units' organization unchanged
    updated_unit1 = await Unit.fetch_by_unit_id(db_conn, "unit-a", TEST_GUILD_ID)
    updated_unit2 = await Unit.fetch_by_unit_id(db_conn, "unit-b", TEST_GUILD_ID)
    assert updated_unit1.organization == 8
    assert updated_unit2.organization == 6


# Phase 2: Partial payment and organization penalty tests

@pytest.mark.asyncio
async def test_upkeep_partial_payment_single_resource_short(db_conn, test_server):
    """Test organization penalty when short on a single resource type."""
    # Create character
    character = Character(
        identifier="partial-char", name="Partial Payer",
        channel_id=999000000000000003, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "partial-char", TEST_GUILD_ID)

    # Create unit with upkeep costs
    unit = Unit(
        unit_id="unit-partial", name="Partial Unit", unit_type="infantry",
        owner_character_id=character.id,
        organization=10, max_organization=10,
        upkeep_ore=10, upkeep_lumber=5, upkeep_coal=0,
        upkeep_rations=0, upkeep_cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "unit-partial", TEST_GUILD_ID)

    # Create player resources (short on ore by 3)
    resources = PlayerResources(
        character_id=character.id,
        ore=7, lumber=10, coal=0, rations=0, cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify UPKEEP_DEFICIT event generated for unit
    deficit_events = [e for e in events if e.event_type == 'UPKEEP_DEFICIT']
    assert len(deficit_events) == 1
    deficit_event = deficit_events[0]
    assert deficit_event.entity_id == unit.id
    assert deficit_event.event_data['unit_id'] == 'unit-partial'
    assert deficit_event.event_data['resources_deficit'] == {'ore': 3}
    assert deficit_event.event_data['organization_penalty'] == 3
    assert deficit_event.event_data['new_organization'] == 7  # 10 - 3
    assert deficit_event.event_data['affected_character_ids'] == [character.id]

    # Verify UPKEEP_SUMMARY event also generated
    summary_events = [e for e in events if e.event_type == 'UPKEEP_SUMMARY']
    assert len(summary_events) == 1
    assert summary_events[0].event_data['resources_spent']['ore'] == 7  # All available
    assert summary_events[0].event_data['resources_spent']['lumber'] == 5

    # Verify resources were deducted (all ore consumed)
    updated_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert updated_resources.ore == 0
    assert updated_resources.lumber == 5

    # Verify unit organization reduced
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-partial", TEST_GUILD_ID)
    assert updated_unit.organization == 7  # 10 - 3


@pytest.mark.asyncio
async def test_upkeep_partial_payment_multiple_resources_short(db_conn, test_server):
    """Test organization penalty when short on multiple resource types."""
    # Create character
    character = Character(
        identifier="multi-short-char", name="Multi Short Payer",
        channel_id=999000000000000004, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "multi-short-char", TEST_GUILD_ID)

    # Create unit with upkeep costs
    unit = Unit(
        unit_id="unit-multi-short", name="Multi Short Unit", unit_type="infantry",
        owner_character_id=character.id,
        organization=10, max_organization=10,
        upkeep_ore=5, upkeep_lumber=5, upkeep_coal=5,
        upkeep_rations=0, upkeep_cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Create player resources (short on ore by 2, lumber by 1)
    resources = PlayerResources(
        character_id=character.id,
        ore=3, lumber=4, coal=10, rations=0, cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify UPKEEP_DEFICIT event
    deficit_events = [e for e in events if e.event_type == 'UPKEEP_DEFICIT']
    assert len(deficit_events) == 1
    deficit_event = deficit_events[0]
    assert deficit_event.event_data['resources_deficit'] == {'ore': 2, 'lumber': 1}
    assert deficit_event.event_data['organization_penalty'] == 3  # 2 + 1
    assert deficit_event.event_data['new_organization'] == 7  # 10 - 3

    # Verify resources consumed
    updated_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert updated_resources.ore == 0
    assert updated_resources.lumber == 0
    assert updated_resources.coal == 5  # 10 - 5

    # Verify unit organization reduced
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-multi-short", TEST_GUILD_ID)
    assert updated_unit.organization == 7


@pytest.mark.asyncio
async def test_upkeep_no_resources(db_conn, test_server):
    """Test organization penalty when player has no resources at all."""
    # Create character
    character = Character(
        identifier="no-res-char", name="No Resources Player",
        channel_id=999000000000000005, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "no-res-char", TEST_GUILD_ID)

    # Create unit with upkeep costs
    unit = Unit(
        unit_id="unit-no-res", name="Starving Unit", unit_type="infantry",
        owner_character_id=character.id,
        organization=10, max_organization=10,
        upkeep_ore=2, upkeep_lumber=3, upkeep_coal=1,
        upkeep_rations=4, upkeep_cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # No PlayerResources created (player has nothing)

    # Execute upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify UPKEEP_DEFICIT and UPKEEP_TOTAL_DEFICIT events (no UPKEEP_SUMMARY since nothing spent)
    assert len(events) == 2
    deficit_events = [e for e in events if e.event_type == 'UPKEEP_DEFICIT']
    total_deficit_events = [e for e in events if e.event_type == 'UPKEEP_TOTAL_DEFICIT']

    assert len(deficit_events) == 1
    assert len(total_deficit_events) == 1

    deficit_event = deficit_events[0]
    assert deficit_event.event_data['resources_deficit'] == {
        'ore': 2, 'lumber': 3, 'coal': 1, 'rations': 4
    }
    assert deficit_event.event_data['organization_penalty'] == 10  # 2+3+1+4
    assert deficit_event.event_data['new_organization'] == 0  # 10 - 10

    # Verify unit organization reduced to 0
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-no-res", TEST_GUILD_ID)
    assert updated_unit.organization == 0


@pytest.mark.asyncio
async def test_upkeep_organization_can_go_negative(db_conn, test_server):
    """Test that organization can go below 0 without special handling."""
    # Create character
    character = Character(
        identifier="neg-org-char", name="Negative Org Player",
        channel_id=999000000000000006, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "neg-org-char", TEST_GUILD_ID)

    # Create unit with low organization and high upkeep
    unit = Unit(
        unit_id="unit-neg-org", name="Depleted Unit", unit_type="infantry",
        owner_character_id=character.id,
        organization=3, max_organization=10,
        upkeep_ore=5, upkeep_lumber=5, upkeep_coal=5,
        upkeep_rations=0, upkeep_cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # No PlayerResources (all upkeep missing)

    # Execute upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify deficit event
    deficit_event = events[0]
    assert deficit_event.event_data['organization_penalty'] == 15  # 5+5+5
    assert deficit_event.event_data['new_organization'] == -12  # 3 - 15

    # Verify unit organization is negative
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-neg-org", TEST_GUILD_ID)
    assert updated_unit.organization == -12


# Phase 3: Multiple owners and edge cases tests

@pytest.mark.asyncio
async def test_upkeep_multiple_owners(db_conn, test_server):
    """Test upkeep processing for multiple owners with separate resources."""
    # Create two characters
    char1 = Character(
        identifier="owner1", name="Owner One",
        channel_id=999000000000000007, guild_id=TEST_GUILD_ID
    )
    await char1.upsert(db_conn)
    char1 = await Character.fetch_by_identifier(db_conn, "owner1", TEST_GUILD_ID)

    char2 = Character(
        identifier="owner2", name="Owner Two",
        channel_id=999000000000000008, guild_id=TEST_GUILD_ID
    )
    await char2.upsert(db_conn)
    char2 = await Character.fetch_by_identifier(db_conn, "owner2", TEST_GUILD_ID)

    # Create units for each character
    unit1 = Unit(
        unit_id="owner1-unit", name="First Owner Unit", unit_type="infantry",
        owner_character_id=char1.id,
        organization=10, max_organization=10,
        upkeep_ore=5, upkeep_lumber=0, upkeep_coal=0,
        upkeep_rations=0, upkeep_cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await unit1.upsert(db_conn)

    unit2 = Unit(
        unit_id="owner2-unit", name="Second Owner Unit", unit_type="cavalry",
        owner_character_id=char2.id,
        organization=8, max_organization=8,
        upkeep_ore=0, upkeep_lumber=10, upkeep_coal=0,
        upkeep_rations=0, upkeep_cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await unit2.upsert(db_conn)

    # Create resources for each character
    # Owner 1 has enough, Owner 2 is short
    res1 = PlayerResources(
        character_id=char1.id,
        ore=20, lumber=0, coal=0, rations=0, cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await res1.upsert(db_conn)

    res2 = PlayerResources(
        character_id=char2.id,
        ore=0, lumber=5, coal=0, rations=0, cloth=0,  # Short 5 lumber
        guild_id=TEST_GUILD_ID
    )
    await res2.upsert(db_conn)

    # Execute upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify events: 2 UPKEEP_SUMMARY + 1 UPKEEP_DEFICIT
    summary_events = [e for e in events if e.event_type == 'UPKEEP_SUMMARY']
    deficit_events = [e for e in events if e.event_type == 'UPKEEP_DEFICIT']

    assert len(summary_events) == 2
    assert len(deficit_events) == 1

    # Verify Owner 1's summary (full payment)
    owner1_summary = next(e for e in summary_events if e.entity_id == char1.id)
    assert owner1_summary.event_data['resources_spent']['ore'] == 5
    assert owner1_summary.event_data['units_maintained'] == 1

    # Verify Owner 2's summary (partial payment)
    owner2_summary = next(e for e in summary_events if e.entity_id == char2.id)
    assert owner2_summary.event_data['resources_spent']['lumber'] == 5

    # Verify Owner 2's deficit event
    assert deficit_events[0].event_data['resources_deficit'] == {'lumber': 5}
    assert deficit_events[0].event_data['organization_penalty'] == 5

    # Verify resources deducted independently
    updated_res1 = await PlayerResources.fetch_by_character(db_conn, char1.id, TEST_GUILD_ID)
    updated_res2 = await PlayerResources.fetch_by_character(db_conn, char2.id, TEST_GUILD_ID)
    assert updated_res1.ore == 15  # 20 - 5
    assert updated_res2.lumber == 0  # 5 - 5

    # Verify unit organizations
    updated_unit1 = await Unit.fetch_by_unit_id(db_conn, "owner1-unit", TEST_GUILD_ID)
    updated_unit2 = await Unit.fetch_by_unit_id(db_conn, "owner2-unit", TEST_GUILD_ID)
    assert updated_unit1.organization == 10  # Unchanged
    assert updated_unit2.organization == 3  # 8 - 5


@pytest.mark.asyncio
async def test_upkeep_zero_cost_unit(db_conn, test_server):
    """Test unit with zero upkeep costs generates no events."""
    # Create character
    character = Character(
        identifier="zero-cost-char", name="Zero Cost Owner",
        channel_id=999000000000000009, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "zero-cost-char", TEST_GUILD_ID)

    # Create unit with zero upkeep
    unit = Unit(
        unit_id="unit-free", name="Free Unit", unit_type="militia",
        owner_character_id=character.id,
        organization=5, max_organization=5,
        upkeep_ore=0, upkeep_lumber=0, upkeep_coal=0,
        upkeep_rations=0, upkeep_cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Execute upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify no events generated (no resources spent)
    assert len(events) == 0

    # Verify unit organization unchanged
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "unit-free", TEST_GUILD_ID)
    assert updated_unit.organization == 5


@pytest.mark.asyncio
async def test_upkeep_no_units(db_conn, test_server):
    """Test upkeep phase with no units generates no events."""
    # Execute upkeep phase with no units
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify no events generated
    assert len(events) == 0


@pytest.mark.asyncio
async def test_upkeep_multiple_units_same_owner_resource_sharing(db_conn, test_server):
    """Test that resources are consumed in order across multiple units for same owner."""
    # Create character
    character = Character(
        identifier="shared-res-char", name="Shared Resources Owner",
        channel_id=999000000000000010, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "shared-res-char", TEST_GUILD_ID)

    # Create two units that both need ore
    unit1 = Unit(
        unit_id="unit-share-1", name="Share Unit 1", unit_type="infantry",
        owner_character_id=character.id,
        organization=10, max_organization=10,
        upkeep_ore=5, upkeep_lumber=0, upkeep_coal=0,
        upkeep_rations=0, upkeep_cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await unit1.upsert(db_conn)

    unit2 = Unit(
        unit_id="unit-share-2", name="Share Unit 2", unit_type="infantry",
        owner_character_id=character.id,
        organization=10, max_organization=10,
        upkeep_ore=5, upkeep_lumber=0, upkeep_coal=0,
        upkeep_rations=0, upkeep_cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await unit2.upsert(db_conn)

    # Only 7 ore available (first unit gets 5, second gets 2)
    resources = PlayerResources(
        character_id=character.id,
        ore=7, lumber=0, coal=0, rations=0, cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify summary shows all ore spent
    summary_events = [e for e in events if e.event_type == 'UPKEEP_SUMMARY']
    assert len(summary_events) == 1
    assert summary_events[0].event_data['resources_spent']['ore'] == 7

    # Verify deficit event for second unit (missing 3 ore)
    deficit_events = [e for e in events if e.event_type == 'UPKEEP_DEFICIT']
    assert len(deficit_events) == 1
    assert deficit_events[0].event_data['resources_deficit'] == {'ore': 3}
    assert deficit_events[0].event_data['organization_penalty'] == 3

    # Verify resources depleted
    updated_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert updated_resources.ore == 0

    # Verify one unit ok, one penalized
    # Note: order depends on fetch_all ordering (by unit_id)
    updated_unit1 = await Unit.fetch_by_unit_id(db_conn, "unit-share-1", TEST_GUILD_ID)
    updated_unit2 = await Unit.fetch_by_unit_id(db_conn, "unit-share-2", TEST_GUILD_ID)
    # First unit gets full payment, second unit gets partial
    assert updated_unit1.organization == 10  # Full payment
    assert updated_unit2.organization == 7   # 10 - 3


# Phase 4: Event formatting tests

def test_upkeep_summary_character_line_format():
    """Test UPKEEP_SUMMARY character line formatting."""
    event_data = {
        'character_name': 'Test Player',
        'resources_spent': {
            'ore': 10,
            'lumber': 5,
            'coal': 0,
            'rations': 20,
            'cloth': 3
        },
        'units_maintained': 3,
        'affected_character_ids': [123]
    }
    line = upkeep_summary_character_line(event_data)
    assert 'Upkeep paid' in line
    assert 'ore:10' in line
    assert 'lumber:5' in line
    assert 'coal' not in line  # 0 should be omitted
    assert 'rations:20' in line
    assert 'cloth:3' in line
    assert '3 units' in line


def test_upkeep_summary_character_line_single_unit():
    """Test singular 'unit' when only 1 unit maintained."""
    event_data = {
        'character_name': 'Solo Player',
        'resources_spent': {'ore': 5, 'lumber': 0, 'coal': 0, 'rations': 0, 'cloth': 0},
        'units_maintained': 1,
        'affected_character_ids': [123]
    }
    line = upkeep_summary_character_line(event_data)
    assert '1 unit)' in line  # singular


def test_upkeep_summary_gm_line_format():
    """Test UPKEEP_SUMMARY GM line formatting."""
    event_data = {
        'character_name': 'Test Player',
        'resources_spent': {
            'ore': 10,
            'lumber': 5,
            'coal': 0,
            'rations': 0,
            'cloth': 0
        },
        'units_maintained': 2,
        'affected_character_ids': [123]
    }
    line = upkeep_summary_gm_line(event_data)
    assert 'Test Player' in line
    assert 'ore:10' in line
    assert 'lumber:5' in line
    assert '2u' in line  # abbreviated units count


def test_upkeep_deficit_character_line_format():
    """Test UPKEEP_DEFICIT character line formatting."""
    event_data = {
        'unit_id': 'unit-test',
        'unit_name': 'Test Unit',
        'resources_deficit': {
            'ore': 3,
            'lumber': 2
        },
        'organization_penalty': 5,
        'new_organization': 5,
        'affected_character_ids': [123]
    }
    line = upkeep_deficit_character_line(event_data)
    assert 'unit-test' in line
    assert 'Insufficient upkeep' in line
    assert 'ore:3' in line
    assert 'lumber:2' in line
    assert '-5' in line
    assert '5' in line  # new organization


def test_upkeep_deficit_gm_line_format():
    """Test UPKEEP_DEFICIT GM line formatting."""
    event_data = {
        'unit_id': 'unit-test',
        'resources_deficit': {'ore': 3},
        'organization_penalty': 3,
        'new_organization': 7,
        'affected_character_ids': [123]
    }
    line = upkeep_deficit_gm_line(event_data)
    assert 'unit-test' in line
    assert 'org -3' in line


def test_upkeep_total_deficit_character_line_format():
    """Test UPKEEP_TOTAL_DEFICIT character line formatting."""
    event_data = {
        'character_name': 'Test Player',
        'total_deficit': {
            'rations': 7,
            'cloth': 6
        },
        'units_affected': 3,
        'affected_character_ids': [123]
    }
    line = upkeep_total_deficit_character_line(event_data)
    assert 'Total resources lacking' in line
    assert '7 rations' in line
    assert '6 cloth' in line
    assert '3 units' in line


def test_upkeep_total_deficit_gm_line_empty():
    """Test UPKEEP_TOTAL_DEFICIT GM line returns empty (not shown in GM report)."""
    event_data = {
        'character_name': 'Test Player',
        'total_deficit': {'rations': 5},
        'units_affected': 2,
        'affected_character_ids': [123]
    }
    line = upkeep_total_deficit_gm_line(event_data)
    assert line == ""


@pytest.mark.asyncio
async def test_upkeep_total_deficit_event_generated(db_conn, test_server):
    """Test that UPKEEP_TOTAL_DEFICIT event is generated when units have deficits."""
    # Create character
    character = Character(
        identifier="total-deficit-char", name="Total Deficit Player",
        channel_id=999000000000000011, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "total-deficit-char", TEST_GUILD_ID)

    # Create two units with upkeep costs
    unit1 = Unit(
        unit_id="deficit-unit-1", name="Deficit Unit 1", unit_type="infantry",
        owner_character_id=character.id,
        organization=10, max_organization=10,
        upkeep_ore=0, upkeep_lumber=0, upkeep_coal=0,
        upkeep_rations=5, upkeep_cloth=2,
        guild_id=TEST_GUILD_ID
    )
    await unit1.upsert(db_conn)

    unit2 = Unit(
        unit_id="deficit-unit-2", name="Deficit Unit 2", unit_type="infantry",
        owner_character_id=character.id,
        organization=10, max_organization=10,
        upkeep_ore=0, upkeep_lumber=0, upkeep_coal=0,
        upkeep_rations=5, upkeep_cloth=2,
        guild_id=TEST_GUILD_ID
    )
    await unit2.upsert(db_conn)

    # Create resources that can only partially cover upkeep
    # Need: 10 rations, 4 cloth. Have: 3 rations, 1 cloth
    resources = PlayerResources(
        character_id=character.id,
        ore=0, lumber=0, coal=0, rations=3, cloth=1,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Execute upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify UPKEEP_TOTAL_DEFICIT event generated
    total_deficit_events = [e for e in events if e.event_type == 'UPKEEP_TOTAL_DEFICIT']
    assert len(total_deficit_events) == 1

    event = total_deficit_events[0]
    assert event.entity_id == character.id
    assert event.event_data['units_affected'] == 2
    # Total deficit: needed 10 rations, had 3 = 7 missing; needed 4 cloth, had 1 = 3 missing
    assert event.event_data['total_deficit']['rations'] == 7
    assert event.event_data['total_deficit']['cloth'] == 3
    assert event.event_data['affected_character_ids'] == [character.id]


# Commander notification tests

@pytest.mark.asyncio
async def test_upkeep_deficit_commander_notified(db_conn, test_server):
    """Test that commander is included in affected_character_ids when different from owner."""
    # Create owner character
    owner = Character(
        identifier="unit-owner", name="Unit Owner",
        channel_id=999000000000000012, guild_id=TEST_GUILD_ID
    )
    await owner.upsert(db_conn)
    owner = await Character.fetch_by_identifier(db_conn, "unit-owner", TEST_GUILD_ID)

    # Create commander character
    commander = Character(
        identifier="unit-commander", name="Unit Commander",
        channel_id=999000000000000013, guild_id=TEST_GUILD_ID
    )
    await commander.upsert(db_conn)
    commander = await Character.fetch_by_identifier(db_conn, "unit-commander", TEST_GUILD_ID)

    # Create unit with different owner and commander
    unit = Unit(
        unit_id="commanded-unit", name="Commanded Unit", unit_type="infantry",
        owner_character_id=owner.id,
        commander_character_id=commander.id,
        organization=10, max_organization=10,
        upkeep_ore=5, upkeep_lumber=0, upkeep_coal=0,
        upkeep_rations=0, upkeep_cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # No resources available - will cause deficit
    # Execute upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify UPKEEP_DEFICIT event includes both owner and commander
    deficit_events = [e for e in events if e.event_type == 'UPKEEP_DEFICIT']
    assert len(deficit_events) == 1

    event = deficit_events[0]
    assert owner.id in event.event_data['affected_character_ids']
    assert commander.id in event.event_data['affected_character_ids']
    assert event.event_data['owner_character_id'] == owner.id
    assert event.event_data['owner_name'] == 'Unit Owner'


@pytest.mark.asyncio
async def test_upkeep_deficit_no_commander(db_conn, test_server):
    """Test that when no commander, only owner is in affected_character_ids."""
    # Create owner character
    owner = Character(
        identifier="solo-owner", name="Solo Owner",
        channel_id=999000000000000014, guild_id=TEST_GUILD_ID
    )
    await owner.upsert(db_conn)
    owner = await Character.fetch_by_identifier(db_conn, "solo-owner", TEST_GUILD_ID)

    # Create unit with no commander
    unit = Unit(
        unit_id="no-commander-unit", name="No Commander Unit", unit_type="infantry",
        owner_character_id=owner.id,
        commander_character_id=None,
        organization=10, max_organization=10,
        upkeep_ore=5, upkeep_lumber=0, upkeep_coal=0,
        upkeep_rations=0, upkeep_cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Execute upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify UPKEEP_DEFICIT event only has owner
    deficit_events = [e for e in events if e.event_type == 'UPKEEP_DEFICIT']
    assert len(deficit_events) == 1

    event = deficit_events[0]
    assert event.event_data['affected_character_ids'] == [owner.id]


@pytest.mark.asyncio
async def test_upkeep_deficit_commander_is_owner(db_conn, test_server):
    """Test that when commander equals owner, only one entry in affected_character_ids."""
    # Create owner character (also the commander)
    owner = Character(
        identifier="owner-commander", name="Owner Commander",
        channel_id=999000000000000015, guild_id=TEST_GUILD_ID
    )
    await owner.upsert(db_conn)
    owner = await Character.fetch_by_identifier(db_conn, "owner-commander", TEST_GUILD_ID)

    # Create unit where commander is same as owner
    unit = Unit(
        unit_id="self-commanded-unit", name="Self Commanded Unit", unit_type="infantry",
        owner_character_id=owner.id,
        commander_character_id=owner.id,
        organization=10, max_organization=10,
        upkeep_ore=5, upkeep_lumber=0, upkeep_coal=0,
        upkeep_rations=0, upkeep_cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Execute upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify UPKEEP_DEFICIT event only has one entry (no duplicate)
    deficit_events = [e for e in events if e.event_type == 'UPKEEP_DEFICIT']
    assert len(deficit_events) == 1

    event = deficit_events[0]
    assert event.event_data['affected_character_ids'] == [owner.id]


def test_upkeep_deficit_owner_view_format():
    """Test UPKEEP_DEFICIT character line formatting for owner view."""
    event_data = {
        'unit_id': 'unit-test',
        'unit_name': 'Test Unit',
        'resources_deficit': {'ore': 3},
        'organization_penalty': 3,
        'new_organization': 7,
        'owner_character_id': 123,
        'owner_name': 'Owner Name',
        'affected_character_ids': [123, 456]
    }
    # Owner viewing their own unit
    line = upkeep_deficit_character_line(event_data, character_id=123)
    assert 'unit-test' in line
    assert 'Insufficient upkeep' in line
    assert 'owned by' not in line  # Owner doesn't see "owned by" text


def test_upkeep_deficit_commander_view_format():
    """Test UPKEEP_DEFICIT character line formatting for commander view."""
    event_data = {
        'unit_id': 'unit-test',
        'unit_name': 'Test Unit',
        'resources_deficit': {'ore': 3},
        'organization_penalty': 3,
        'new_organization': 7,
        'owner_character_id': 123,
        'owner_name': 'Owner Name',
        'affected_character_ids': [123, 456]
    }
    # Commander (456) viewing a unit they don't own
    line = upkeep_deficit_character_line(event_data, character_id=456)
    assert 'unit-test' in line
    assert 'owned by Owner Name' in line  # Commander sees owner info
    assert 'Insufficient upkeep' in line
