"""
Pytest tests for the organization phase in turn resolution.
Tests verify unit disbanding, organization recovery, and event generation.

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_organization_phase.py -v
"""
import pytest
from handlers.turn_handlers import (
    execute_organization_phase,
    disband_low_organization_units,
    recover_organization_in_friendly_territory
)
from db import Character, Unit, Territory, Faction, FactionMember, WargameConfig
from order_types import TurnPhase
from tests.conftest import TEST_GUILD_ID


async def cleanup_org_test_data(db_conn):
    """Helper to clean up organization test data."""
    await db_conn.execute("DELETE FROM TurnLog WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_disband_unit_with_zero_organization(db_conn, test_server):
    """Test that a unit with organization = 0 is disbanded."""
    try:
        # Create owner character
        owner = Character(
            identifier="org-owner", name="Org Owner",
            channel_id=999000000000000001, guild_id=TEST_GUILD_ID
        )
        await owner.upsert(db_conn)
        owner = await Character.fetch_by_identifier(db_conn, "org-owner", TEST_GUILD_ID)

        # Create unit with org = 0
        unit = Unit(
            unit_id="disband-test-1", name="Disbanding Unit", unit_type="infantry",
            owner_character_id=owner.id,
            organization=0, max_organization=10,
            status='ACTIVE',
            guild_id=TEST_GUILD_ID
        )
        await unit.upsert(db_conn)

        # Execute organization phase
        events = await execute_organization_phase(db_conn, TEST_GUILD_ID, 1)

        # Verify UNIT_DISBANDED event
        disband_events = [e for e in events if e.event_type == 'UNIT_DISBANDED']
        assert len(disband_events) == 1
        event = disband_events[0]
        assert event.event_data['unit_id'] == 'disband-test-1'
        assert owner.id in event.event_data['affected_character_ids']

        # Verify unit status changed
        updated_unit = await Unit.fetch_by_unit_id(db_conn, "disband-test-1", TEST_GUILD_ID)
        assert updated_unit.status == 'DISBANDED'
    finally:
        await cleanup_org_test_data(db_conn)


@pytest.mark.asyncio
async def test_disband_unit_with_negative_organization(db_conn, test_server):
    """Test that a unit with negative organization is disbanded."""
    try:
        owner = Character(
            identifier="neg-org-owner", name="Neg Org Owner",
            channel_id=999000000000000002, guild_id=TEST_GUILD_ID
        )
        await owner.upsert(db_conn)
        owner = await Character.fetch_by_identifier(db_conn, "neg-org-owner", TEST_GUILD_ID)

        unit = Unit(
            unit_id="disband-neg", name="Negative Org Unit", unit_type="infantry",
            owner_character_id=owner.id,
            organization=-5, max_organization=10,
            status='ACTIVE',
            guild_id=TEST_GUILD_ID
        )
        await unit.upsert(db_conn)

        events = await execute_organization_phase(db_conn, TEST_GUILD_ID, 1)

        disband_events = [e for e in events if e.event_type == 'UNIT_DISBANDED']
        assert len(disband_events) == 1
        assert disband_events[0].event_data['final_organization'] == -5

        updated_unit = await Unit.fetch_by_unit_id(db_conn, "disband-neg", TEST_GUILD_ID)
        assert updated_unit.status == 'DISBANDED'
    finally:
        await cleanup_org_test_data(db_conn)


@pytest.mark.asyncio
async def test_no_disband_positive_organization(db_conn, test_server):
    """Test that a unit with positive organization is not disbanded."""
    try:
        owner = Character(
            identifier="pos-org-owner", name="Pos Org Owner",
            channel_id=999000000000000003, guild_id=TEST_GUILD_ID
        )
        await owner.upsert(db_conn)
        owner = await Character.fetch_by_identifier(db_conn, "pos-org-owner", TEST_GUILD_ID)

        unit = Unit(
            unit_id="no-disband", name="Healthy Unit", unit_type="infantry",
            owner_character_id=owner.id,
            organization=5, max_organization=10,
            status='ACTIVE',
            guild_id=TEST_GUILD_ID
        )
        await unit.upsert(db_conn)

        events = await execute_organization_phase(db_conn, TEST_GUILD_ID, 1)

        # No disband events
        disband_events = [e for e in events if e.event_type == 'UNIT_DISBANDED']
        assert len(disband_events) == 0

        # Unit still active
        updated_unit = await Unit.fetch_by_unit_id(db_conn, "no-disband", TEST_GUILD_ID)
        assert updated_unit.status == 'ACTIVE'
    finally:
        await cleanup_org_test_data(db_conn)


@pytest.mark.asyncio
async def test_commander_notified_on_disband(db_conn, test_server):
    """Test that commander is included in affected_character_ids when disbanded."""
    try:
        owner = Character(
            identifier="disband-owner", name="Disband Owner",
            channel_id=999000000000000004, guild_id=TEST_GUILD_ID
        )
        await owner.upsert(db_conn)
        owner = await Character.fetch_by_identifier(db_conn, "disband-owner", TEST_GUILD_ID)

        commander = Character(
            identifier="disband-commander", name="Disband Commander",
            channel_id=999000000000000005, guild_id=TEST_GUILD_ID
        )
        await commander.upsert(db_conn)
        commander = await Character.fetch_by_identifier(db_conn, "disband-commander", TEST_GUILD_ID)

        unit = Unit(
            unit_id="cmd-disband", name="Commanded Disbanding", unit_type="infantry",
            owner_character_id=owner.id,
            commander_character_id=commander.id,
            organization=0, max_organization=10,
            status='ACTIVE',
            guild_id=TEST_GUILD_ID
        )
        await unit.upsert(db_conn)

        events = await execute_organization_phase(db_conn, TEST_GUILD_ID, 1)

        disband_events = [e for e in events if e.event_type == 'UNIT_DISBANDED']
        assert len(disband_events) == 1
        assert owner.id in disband_events[0].event_data['affected_character_ids']
        assert commander.id in disband_events[0].event_data['affected_character_ids']
    finally:
        await cleanup_org_test_data(db_conn)


@pytest.mark.asyncio
async def test_org_recovery_in_friendly_territory(db_conn, test_server):
    """Test organization recovery in territory controlled by faction member."""
    try:
        # Create faction
        faction = Faction(
            faction_id="test-faction", name="Test Faction",
            guild_id=TEST_GUILD_ID
        )
        await faction.upsert(db_conn)
        faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

        # Create owner
        owner = Character(
            identifier="recovery-owner", name="Recovery Owner",
            channel_id=999000000000000006, guild_id=TEST_GUILD_ID
        )
        await owner.upsert(db_conn)
        owner = await Character.fetch_by_identifier(db_conn, "recovery-owner", TEST_GUILD_ID)

        # Add owner to faction
        fm = FactionMember(
            faction_id=faction.id, character_id=owner.id,
            joined_turn=0, guild_id=TEST_GUILD_ID
        )
        await fm.insert(db_conn)

        # Create territory controlled by owner
        territory = Territory(
            territory_id=100, name="Friendly Land", terrain_type="plains",
            controller_character_id=owner.id,
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)

        # Create unit in that territory
        unit = Unit(
            unit_id="recover-unit", name="Recovering Unit", unit_type="infantry",
            owner_character_id=owner.id,
            faction_id=faction.id,
            current_territory_id=100,
            organization=5, max_organization=10,
            status='ACTIVE',
            guild_id=TEST_GUILD_ID
        )
        await unit.upsert(db_conn)

        events = await execute_organization_phase(db_conn, TEST_GUILD_ID, 1)

        # Verify ORG_RECOVERY event
        recovery_events = [e for e in events if e.event_type == 'ORG_RECOVERY']
        assert len(recovery_events) == 1
        assert recovery_events[0].event_data['old_organization'] == 5
        assert recovery_events[0].event_data['new_organization'] == 6

        # Verify unit organization increased
        updated_unit = await Unit.fetch_by_unit_id(db_conn, "recover-unit", TEST_GUILD_ID)
        assert updated_unit.organization == 6
    finally:
        await cleanup_org_test_data(db_conn)


@pytest.mark.asyncio
async def test_no_recovery_at_max_organization(db_conn, test_server):
    """Test that units at max organization don't recover."""
    try:
        # Create faction
        faction = Faction(
            faction_id="max-org-faction", name="Max Org Faction",
            guild_id=TEST_GUILD_ID
        )
        await faction.upsert(db_conn)
        faction = await Faction.fetch_by_faction_id(db_conn, "max-org-faction", TEST_GUILD_ID)

        # Create owner
        owner = Character(
            identifier="max-org-owner", name="Max Org Owner",
            channel_id=999000000000000007, guild_id=TEST_GUILD_ID
        )
        await owner.upsert(db_conn)
        owner = await Character.fetch_by_identifier(db_conn, "max-org-owner", TEST_GUILD_ID)

        # Add owner to faction
        fm = FactionMember(
            faction_id=faction.id, character_id=owner.id,
            joined_turn=0, guild_id=TEST_GUILD_ID
        )
        await fm.insert(db_conn)

        # Create territory controlled by owner
        territory = Territory(
            territory_id=101, name="Friendly Land 2", terrain_type="plains",
            controller_character_id=owner.id,
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)

        # Create unit at max org
        unit = Unit(
            unit_id="max-org-unit", name="Max Org Unit", unit_type="infantry",
            owner_character_id=owner.id,
            faction_id=faction.id,
            current_territory_id=101,
            organization=10, max_organization=10,
            status='ACTIVE',
            guild_id=TEST_GUILD_ID
        )
        await unit.upsert(db_conn)

        events = await execute_organization_phase(db_conn, TEST_GUILD_ID, 1)

        # Verify no recovery events
        recovery_events = [e for e in events if e.event_type == 'ORG_RECOVERY']
        assert len(recovery_events) == 0

        # Verify unit organization unchanged
        updated_unit = await Unit.fetch_by_unit_id(db_conn, "max-org-unit", TEST_GUILD_ID)
        assert updated_unit.organization == 10
    finally:
        await cleanup_org_test_data(db_conn)


@pytest.mark.asyncio
async def test_no_recovery_in_enemy_territory(db_conn, test_server):
    """Test that units in enemy-controlled territory don't recover."""
    try:
        # Create two factions
        faction1 = Faction(
            faction_id="friendly-faction", name="Friendly Faction",
            guild_id=TEST_GUILD_ID
        )
        await faction1.upsert(db_conn)
        faction1 = await Faction.fetch_by_faction_id(db_conn, "friendly-faction", TEST_GUILD_ID)

        faction2 = Faction(
            faction_id="enemy-faction", name="Enemy Faction",
            guild_id=TEST_GUILD_ID
        )
        await faction2.upsert(db_conn)
        faction2 = await Faction.fetch_by_faction_id(db_conn, "enemy-faction", TEST_GUILD_ID)

        # Create unit owner (in faction1)
        owner = Character(
            identifier="friendly-owner", name="Friendly Owner",
            channel_id=999000000000000008, guild_id=TEST_GUILD_ID
        )
        await owner.upsert(db_conn)
        owner = await Character.fetch_by_identifier(db_conn, "friendly-owner", TEST_GUILD_ID)

        fm1 = FactionMember(
            faction_id=faction1.id, character_id=owner.id,
            joined_turn=0, guild_id=TEST_GUILD_ID
        )
        await fm1.insert(db_conn)

        # Create enemy (in faction2)
        enemy = Character(
            identifier="enemy-owner", name="Enemy Owner",
            channel_id=999000000000000009, guild_id=TEST_GUILD_ID
        )
        await enemy.upsert(db_conn)
        enemy = await Character.fetch_by_identifier(db_conn, "enemy-owner", TEST_GUILD_ID)

        fm2 = FactionMember(
            faction_id=faction2.id, character_id=enemy.id,
            joined_turn=0, guild_id=TEST_GUILD_ID
        )
        await fm2.insert(db_conn)

        # Create territory controlled by enemy
        territory = Territory(
            territory_id=102, name="Enemy Land", terrain_type="plains",
            controller_character_id=enemy.id,
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)

        # Create unit in enemy territory (belonging to faction1)
        unit = Unit(
            unit_id="enemy-terr-unit", name="Unit in Enemy Territory", unit_type="infantry",
            owner_character_id=owner.id,
            faction_id=faction1.id,
            current_territory_id=102,
            organization=5, max_organization=10,
            status='ACTIVE',
            guild_id=TEST_GUILD_ID
        )
        await unit.upsert(db_conn)

        events = await execute_organization_phase(db_conn, TEST_GUILD_ID, 1)

        # Verify no recovery events
        recovery_events = [e for e in events if e.event_type == 'ORG_RECOVERY']
        assert len(recovery_events) == 0

        # Verify unit organization unchanged
        updated_unit = await Unit.fetch_by_unit_id(db_conn, "enemy-terr-unit", TEST_GUILD_ID)
        assert updated_unit.organization == 5
    finally:
        await cleanup_org_test_data(db_conn)


@pytest.mark.asyncio
async def test_disband_reusable_from_combat_phase(db_conn, test_server):
    """Test that disband_low_organization_units works with COMBAT phase parameter."""
    try:
        owner = Character(
            identifier="combat-disband-owner", name="Combat Disband Owner",
            channel_id=999000000000000010, guild_id=TEST_GUILD_ID
        )
        await owner.upsert(db_conn)
        owner = await Character.fetch_by_identifier(db_conn, "combat-disband-owner", TEST_GUILD_ID)

        unit = Unit(
            unit_id="combat-disband", name="Combat Casualty", unit_type="infantry",
            owner_character_id=owner.id,
            organization=0, max_organization=10,
            status='ACTIVE',
            guild_id=TEST_GUILD_ID
        )
        await unit.upsert(db_conn)

        # Call directly with COMBAT phase
        events = await disband_low_organization_units(
            db_conn, TEST_GUILD_ID, 1, TurnPhase.COMBAT.value
        )

        assert len(events) == 1
        assert events[0].phase == 'COMBAT'  # Phase should be COMBAT, not ORGANIZATION
        assert events[0].event_type == 'UNIT_DISBANDED'

        updated_unit = await Unit.fetch_by_unit_id(db_conn, "combat-disband", TEST_GUILD_ID)
        assert updated_unit.status == 'DISBANDED'
    finally:
        await cleanup_org_test_data(db_conn)


@pytest.mark.asyncio
async def test_already_disbanded_units_not_processed(db_conn, test_server):
    """Test that already disbanded units are not processed again."""
    try:
        owner = Character(
            identifier="already-disbanded-owner", name="Already Disbanded Owner",
            channel_id=999000000000000011, guild_id=TEST_GUILD_ID
        )
        await owner.upsert(db_conn)
        owner = await Character.fetch_by_identifier(db_conn, "already-disbanded-owner", TEST_GUILD_ID)

        # Create already disbanded unit with org <= 0
        unit = Unit(
            unit_id="already-disbanded", name="Already Disbanded", unit_type="infantry",
            owner_character_id=owner.id,
            organization=-3, max_organization=10,
            status='DISBANDED',
            guild_id=TEST_GUILD_ID
        )
        await unit.upsert(db_conn)

        events = await execute_organization_phase(db_conn, TEST_GUILD_ID, 1)

        # No events should be generated
        disband_events = [e for e in events if e.event_type == 'UNIT_DISBANDED']
        assert len(disband_events) == 0
    finally:
        await cleanup_org_test_data(db_conn)
