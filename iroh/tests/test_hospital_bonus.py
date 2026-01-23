"""
Pytest tests for hospital building bonus in organization recovery.

Tests verify:
- calculate_hospital_bonus returns correct value
- Unit recovers +3 (1 base + 2 hospital) with one hospital
- Multiple hospitals stack (+1 base + 4 from 2 hospitals = +5)
- DESTROYED hospital doesn't contribute
- Hospital in enemy territory provides no bonus
- Recovery capped at max_organization

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_hospital_bonus.py -v
"""
import pytest
from handlers.turn_handlers import (
    execute_organization_phase,
    recover_organization_in_friendly_territory,
    calculate_hospital_bonus,
    HOSPITAL_BONUS
)
from db import Character, Unit, Territory, Faction, FactionMember, Building, BuildingType
from tests.conftest import TEST_GUILD_ID


@pytest.mark.asyncio
async def test_hospital_bonus_calculation(db_conn, test_server):
    """Test that calculate_hospital_bonus returns correct value for ACTIVE hospitals."""
    # Create territory
    territory = Territory(
        territory_id="H100", name="Hospital Territory", terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create hospital building type
    hospital_type = BuildingType(
        type_id="test-hospital", name="Test Hospital",
        keywords=["hospital"],
        guild_id=TEST_GUILD_ID
    )
    await hospital_type.upsert(db_conn)

    # Create ACTIVE hospital building
    hospital = Building(
        building_id="hospital-1", name="Field Hospital",
        building_type="test-hospital", territory_id="H100",
        durability=10, status="ACTIVE",
        keywords=["hospital"],
        guild_id=TEST_GUILD_ID
    )
    await hospital.upsert(db_conn)

    # Calculate hospital bonus
    bonus = await calculate_hospital_bonus(db_conn, "H100", TEST_GUILD_ID)
    assert bonus == HOSPITAL_BONUS  # Should be 2


@pytest.mark.asyncio
async def test_hospital_bonus_organization_recovery(db_conn, test_server):
    """Test that unit recovers +3 (1 base + 2 hospital) with one hospital."""
    # Create faction
    faction = Faction(
        faction_id="hospital-faction", name="Hospital Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "hospital-faction", TEST_GUILD_ID)

    # Create owner
    owner = Character(
        identifier="hospital-owner", name="Hospital Owner",
        channel_id=999000000000000201, guild_id=TEST_GUILD_ID
    )
    await owner.upsert(db_conn)
    owner = await Character.fetch_by_identifier(db_conn, "hospital-owner", TEST_GUILD_ID)

    # Add owner to faction
    fm = FactionMember(
        faction_id=faction.id, character_id=owner.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await fm.insert(db_conn)

    # Create territory controlled by owner
    territory = Territory(
        territory_id="H101", name="Hospital Land", terrain_type="plains",
        controller_character_id=owner.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create hospital building type
    hospital_type = BuildingType(
        type_id="test-hospital-2", name="Test Hospital",
        keywords=["hospital"],
        guild_id=TEST_GUILD_ID
    )
    await hospital_type.upsert(db_conn)

    # Create ACTIVE hospital building
    hospital = Building(
        building_id="hospital-2", name="Field Hospital",
        building_type="test-hospital-2", territory_id="H101",
        durability=10, status="ACTIVE",
        keywords=["hospital"],
        guild_id=TEST_GUILD_ID
    )
    await hospital.upsert(db_conn)

    # Create unit in that territory with low org
    unit = Unit(
        unit_id="hospital-unit", name="Recovering Unit", unit_type="infantry",
        owner_character_id=owner.id,
        faction_id=faction.id,
        current_territory_id="H101",
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
    assert recovery_events[0].event_data['new_organization'] == 8  # 5 + 1 base + 2 hospital

    # Verify unit organization increased
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "hospital-unit", TEST_GUILD_ID)
    assert updated_unit.organization == 8


@pytest.mark.asyncio
async def test_hospital_bonus_stacking(db_conn, test_server):
    """Test that multiple hospitals stack (+1 base + 4 from 2 hospitals = +5)."""
    # Create faction
    faction = Faction(
        faction_id="stack-faction", name="Stack Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "stack-faction", TEST_GUILD_ID)

    # Create owner
    owner = Character(
        identifier="stack-owner", name="Stack Owner",
        channel_id=999000000000000202, guild_id=TEST_GUILD_ID
    )
    await owner.upsert(db_conn)
    owner = await Character.fetch_by_identifier(db_conn, "stack-owner", TEST_GUILD_ID)

    # Add owner to faction
    fm = FactionMember(
        faction_id=faction.id, character_id=owner.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await fm.insert(db_conn)

    # Create territory controlled by owner
    territory = Territory(
        territory_id="H102", name="Multi Hospital Land", terrain_type="plains",
        controller_character_id=owner.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create hospital building type
    hospital_type = BuildingType(
        type_id="test-hospital-3", name="Test Hospital",
        keywords=["hospital"],
        guild_id=TEST_GUILD_ID
    )
    await hospital_type.upsert(db_conn)

    # Create TWO ACTIVE hospital buildings
    hospital1 = Building(
        building_id="hospital-3a", name="Field Hospital A",
        building_type="test-hospital-3", territory_id="H102",
        durability=10, status="ACTIVE",
        keywords=["hospital"],
        guild_id=TEST_GUILD_ID
    )
    await hospital1.upsert(db_conn)

    hospital2 = Building(
        building_id="hospital-3b", name="Field Hospital B",
        building_type="test-hospital-3", territory_id="H102",
        durability=10, status="ACTIVE",
        keywords=["hospital"],
        guild_id=TEST_GUILD_ID
    )
    await hospital2.upsert(db_conn)

    # Create unit in that territory with low org
    unit = Unit(
        unit_id="stack-unit", name="Stacking Unit", unit_type="infantry",
        owner_character_id=owner.id,
        faction_id=faction.id,
        current_territory_id="H102",
        organization=3, max_organization=15,
        status='ACTIVE',
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    events = await execute_organization_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify ORG_RECOVERY event
    recovery_events = [e for e in events if e.event_type == 'ORG_RECOVERY']
    assert len(recovery_events) == 1
    assert recovery_events[0].event_data['old_organization'] == 3
    assert recovery_events[0].event_data['new_organization'] == 8  # 3 + 1 base + 4 hospitals

    # Verify unit organization increased
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "stack-unit", TEST_GUILD_ID)
    assert updated_unit.organization == 8


@pytest.mark.asyncio
async def test_hospital_destroyed_no_bonus(db_conn, test_server):
    """Test that DESTROYED hospital doesn't contribute bonus."""
    # Create faction
    faction = Faction(
        faction_id="destroyed-faction", name="Destroyed Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "destroyed-faction", TEST_GUILD_ID)

    # Create owner
    owner = Character(
        identifier="destroyed-owner", name="Destroyed Owner",
        channel_id=999000000000000203, guild_id=TEST_GUILD_ID
    )
    await owner.upsert(db_conn)
    owner = await Character.fetch_by_identifier(db_conn, "destroyed-owner", TEST_GUILD_ID)

    # Add owner to faction
    fm = FactionMember(
        faction_id=faction.id, character_id=owner.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await fm.insert(db_conn)

    # Create territory controlled by owner
    territory = Territory(
        territory_id="H103", name="Destroyed Hospital Land", terrain_type="plains",
        controller_character_id=owner.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create hospital building type
    hospital_type = BuildingType(
        type_id="test-hospital-4", name="Test Hospital",
        keywords=["hospital"],
        guild_id=TEST_GUILD_ID
    )
    await hospital_type.upsert(db_conn)

    # Create DESTROYED hospital building
    hospital = Building(
        building_id="hospital-4", name="Destroyed Hospital",
        building_type="test-hospital-4", territory_id="H103",
        durability=0, status="DESTROYED",
        keywords=["hospital"],
        guild_id=TEST_GUILD_ID
    )
    await hospital.upsert(db_conn)

    # Create unit in that territory with low org
    unit = Unit(
        unit_id="destroyed-unit", name="No Bonus Unit", unit_type="infantry",
        owner_character_id=owner.id,
        faction_id=faction.id,
        current_territory_id="H103",
        organization=5, max_organization=10,
        status='ACTIVE',
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    events = await execute_organization_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify ORG_RECOVERY event - only base recovery (+1)
    recovery_events = [e for e in events if e.event_type == 'ORG_RECOVERY']
    assert len(recovery_events) == 1
    assert recovery_events[0].event_data['old_organization'] == 5
    assert recovery_events[0].event_data['new_organization'] == 6  # 5 + 1 base only

    # Verify unit organization increased by base only
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "destroyed-unit", TEST_GUILD_ID)
    assert updated_unit.organization == 6


@pytest.mark.asyncio
async def test_hospital_no_bonus_enemy_territory(db_conn, test_server):
    """Test that hospital in enemy territory provides no bonus."""
    # Create two factions
    faction1 = Faction(
        faction_id="enemy-hosp-friendly", name="Friendly Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "enemy-hosp-friendly", TEST_GUILD_ID)

    faction2 = Faction(
        faction_id="enemy-hosp-enemy", name="Enemy Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "enemy-hosp-enemy", TEST_GUILD_ID)

    # Create unit owner (in faction1)
    owner = Character(
        identifier="enemy-hosp-owner", name="Friendly Owner",
        channel_id=999000000000000204, guild_id=TEST_GUILD_ID
    )
    await owner.upsert(db_conn)
    owner = await Character.fetch_by_identifier(db_conn, "enemy-hosp-owner", TEST_GUILD_ID)

    fm1 = FactionMember(
        faction_id=faction1.id, character_id=owner.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await fm1.insert(db_conn)

    # Create enemy (in faction2)
    enemy = Character(
        identifier="enemy-hosp-enemy-char", name="Enemy Owner",
        channel_id=999000000000000205, guild_id=TEST_GUILD_ID
    )
    await enemy.upsert(db_conn)
    enemy = await Character.fetch_by_identifier(db_conn, "enemy-hosp-enemy-char", TEST_GUILD_ID)

    fm2 = FactionMember(
        faction_id=faction2.id, character_id=enemy.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await fm2.insert(db_conn)

    # Create territory controlled by enemy
    territory = Territory(
        territory_id="H104", name="Enemy Hospital Land", terrain_type="plains",
        controller_character_id=enemy.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create hospital building type
    hospital_type = BuildingType(
        type_id="test-hospital-5", name="Test Hospital",
        keywords=["hospital"],
        guild_id=TEST_GUILD_ID
    )
    await hospital_type.upsert(db_conn)

    # Create ACTIVE hospital building in enemy territory
    hospital = Building(
        building_id="hospital-5", name="Enemy Hospital",
        building_type="test-hospital-5", territory_id="H104",
        durability=10, status="ACTIVE",
        keywords=["hospital"],
        guild_id=TEST_GUILD_ID
    )
    await hospital.upsert(db_conn)

    # Create unit in enemy territory (belonging to faction1)
    unit = Unit(
        unit_id="enemy-hosp-unit", name="Unit in Enemy Territory", unit_type="infantry",
        owner_character_id=owner.id,
        faction_id=faction1.id,
        current_territory_id="H104",
        organization=5, max_organization=10,
        status='ACTIVE',
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    events = await execute_organization_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify no recovery events (enemy territory = no recovery at all)
    recovery_events = [e for e in events if e.event_type == 'ORG_RECOVERY']
    assert len(recovery_events) == 0

    # Verify unit organization unchanged
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "enemy-hosp-unit", TEST_GUILD_ID)
    assert updated_unit.organization == 5


@pytest.mark.asyncio
async def test_hospital_bonus_capped_at_max(db_conn, test_server):
    """Test that recovery (base + hospital bonus) is capped at max_organization."""
    # Create faction
    faction = Faction(
        faction_id="cap-faction", name="Cap Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "cap-faction", TEST_GUILD_ID)

    # Create owner
    owner = Character(
        identifier="cap-owner", name="Cap Owner",
        channel_id=999000000000000206, guild_id=TEST_GUILD_ID
    )
    await owner.upsert(db_conn)
    owner = await Character.fetch_by_identifier(db_conn, "cap-owner", TEST_GUILD_ID)

    # Add owner to faction
    fm = FactionMember(
        faction_id=faction.id, character_id=owner.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await fm.insert(db_conn)

    # Create territory controlled by owner
    territory = Territory(
        territory_id="H105", name="Cap Hospital Land", terrain_type="plains",
        controller_character_id=owner.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create hospital building type
    hospital_type = BuildingType(
        type_id="test-hospital-6", name="Test Hospital",
        keywords=["hospital"],
        guild_id=TEST_GUILD_ID
    )
    await hospital_type.upsert(db_conn)

    # Create ACTIVE hospital building
    hospital = Building(
        building_id="hospital-6", name="Field Hospital",
        building_type="test-hospital-6", territory_id="H105",
        durability=10, status="ACTIVE",
        keywords=["hospital"],
        guild_id=TEST_GUILD_ID
    )
    await hospital.upsert(db_conn)

    # Create unit in that territory with org close to max
    # org=9, max=10, would recover +3 but should cap at 10
    unit = Unit(
        unit_id="cap-unit", name="Capped Unit", unit_type="infantry",
        owner_character_id=owner.id,
        faction_id=faction.id,
        current_territory_id="H105",
        organization=9, max_organization=10,
        status='ACTIVE',
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    events = await execute_organization_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify ORG_RECOVERY event - capped at max
    recovery_events = [e for e in events if e.event_type == 'ORG_RECOVERY']
    assert len(recovery_events) == 1
    assert recovery_events[0].event_data['old_organization'] == 9
    assert recovery_events[0].event_data['new_organization'] == 10  # Capped at max, not 9 + 3 = 12

    # Verify unit organization capped at max
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "cap-unit", TEST_GUILD_ID)
    assert updated_unit.organization == 10
