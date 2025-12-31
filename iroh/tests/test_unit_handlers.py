"""
Pytest tests for unit handlers.
Tests verify unit creation, deletion, and commander assignment operations.

Run with: pytest tests/test_unit_handlers.py -v
"""
import pytest
from handlers.unit_handlers import create_unit, delete_unit, set_unit_commander
from db import (
    Character, Faction, FactionMember, Territory, UnitType, Unit, WargameConfig
)
from tests.conftest import TEST_GUILD_ID, TEST_GUILD_ID_2


@pytest.mark.asyncio
async def test_create_unit_success(db_conn, test_server):
    """Test creating a unit with valid parameters."""
    # Create character
    char = Character(
        identifier="unit-owner", name="Unit Owner",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "unit-owner", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add character to faction
    member = FactionMember(
        faction_id=faction.id, character_id=char.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member.insert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # Create territory
    territory = Territory(
        territory_id=1, terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create unit
    success, message = await create_unit(
        db_conn, "UNIT-001", "infantry", "unit-owner", 1, TEST_GUILD_ID
    )

    # Verify
    assert success is True
    assert "created successfully" in message.lower()

    # Verify unit exists in database with correct stats
    unit = await Unit.fetch_by_unit_id(db_conn, "UNIT-001", TEST_GUILD_ID)
    assert unit is not None
    assert unit.unit_type == "infantry"
    assert unit.owner_character_id == char.id
    assert unit.faction_id == faction.id
    assert unit.movement == 2
    assert unit.organization == 10
    assert unit.attack == 5

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_create_unit_duplicate(db_conn, test_server):
    """Test creating a unit with duplicate unit_id."""
    # Create character
    char = Character(
        identifier="unit-owner", name="Unit Owner",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "unit-owner", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add character to faction
    member = FactionMember(
        faction_id=faction.id, character_id=char.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member.insert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # Create territory
    territory = Territory(
        territory_id=1, terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create first unit
    success1, _ = await create_unit(
        db_conn, "UNIT-001", "infantry", "unit-owner", 1, TEST_GUILD_ID
    )
    assert success1 is True

    # Try to create duplicate
    success2, message = await create_unit(
        db_conn, "UNIT-001", "infantry", "unit-owner", 1, TEST_GUILD_ID
    )

    # Verify failure
    assert success2 is False
    assert "already exists" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_create_unit_nonexistent_owner(db_conn, test_server):
    """Test creating a unit with invalid owner identifier."""
    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # Create territory
    territory = Territory(
        territory_id=1, terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Try to create unit with nonexistent owner
    success, message = await create_unit(
        db_conn, "UNIT-001", "infantry", "nonexistent-owner", 1, TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_create_unit_owner_not_in_faction(db_conn, test_server):
    """Test creating a unit when owner is not in a faction."""
    # Create character not in any faction
    char = Character(
        identifier="solo-char", name="Solo Character",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # Create territory
    territory = Territory(
        territory_id=1, terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create unit (should succeed with null faction_id)
    success, message = await create_unit(
        db_conn, "UNIT-001", "infantry", "solo-char", 1, TEST_GUILD_ID
    )

    # Verify success (owner without faction is allowed)
    assert success is True

    # Verify unit has null faction_id
    unit = await Unit.fetch_by_unit_id(db_conn, "UNIT-001", TEST_GUILD_ID)
    assert unit.faction_id is None

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_create_unit_nonexistent_territory(db_conn, test_server):
    """Test creating a unit in non-existent territory."""
    # Create character
    char = Character(
        identifier="unit-owner", name="Unit Owner",
        user_id=100000000000000003, channel_id=900000000000000003,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # Try to create unit in nonexistent territory
    success, message = await create_unit(
        db_conn, "UNIT-001", "infantry", "unit-owner", 999, TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_create_unit_nonexistent_unit_type(db_conn, test_server):
    """Test creating a unit with invalid unit type."""
    # Create character
    char = Character(
        identifier="unit-owner", name="Unit Owner",
        user_id=100000000000000004, channel_id=900000000000000004,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # Create territory
    territory = Territory(
        territory_id=1, terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Try to create unit with nonexistent unit type
    success, message = await create_unit(
        db_conn, "UNIT-001", "nonexistent-type", "unit-owner", 1, TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_create_unit_stats_copied_from_type(db_conn, test_server):
    """Test that unit stats are correctly copied from unit type."""
    # Create character
    char = Character(
        identifier="unit-owner", name="Unit Owner",
        user_id=100000000000000005, channel_id=900000000000000005,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # Create unit type with specific stats
    unit_type = UnitType(
        type_id="custom-unit", name="Custom Unit",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=3, organization=12, attack=7, defense=6,
        siege_attack=4, siege_defense=5, size=2, capacity=10,
        cost_ore=10, cost_lumber=5, cost_coal=3, cost_rations=20, cost_cloth=8,
        upkeep_rations=4, upkeep_cloth=2, is_naval=True
    )
    await unit_type.upsert(db_conn)

    # Create territory
    territory = Territory(
        territory_id=1, terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create unit
    success, _ = await create_unit(
        db_conn, "UNIT-001", "custom-unit", "unit-owner", 1, TEST_GUILD_ID
    )
    assert success is True

    # Verify all stats copied correctly
    unit = await Unit.fetch_by_unit_id(db_conn, "UNIT-001", TEST_GUILD_ID)
    assert unit.movement == 3
    assert unit.organization == 12
    assert unit.max_organization == 12
    assert unit.attack == 7
    assert unit.defense == 6
    assert unit.siege_attack == 4
    assert unit.siege_defense == 5
    assert unit.size == 2
    assert unit.capacity == 10
    assert unit.is_naval is True
    assert unit.upkeep_rations == 4
    assert unit.upkeep_cloth == 2

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_delete_unit_success(db_conn, test_server):
    """Test deleting a unit."""
    # Create character
    char = Character(
        identifier="unit-owner", name="Unit Owner",
        user_id=100000000000000006, channel_id=900000000000000006,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "unit-owner", TEST_GUILD_ID)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # Create territory
    territory = Territory(
        territory_id=1, terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create unit
    unit = Unit(
        unit_id="UNIT-001", name="Test Unit",
        unit_type="infantry",
        owner_character_id=char.id,
        current_territory_id=1, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit.upsert(db_conn)

    # Delete unit
    success, message = await delete_unit(db_conn, "UNIT-001", TEST_GUILD_ID)

    # Verify
    assert success is True
    assert "deleted" in message.lower()

    # Verify unit deleted from database
    fetched = await Unit.fetch_by_unit_id(db_conn, "UNIT-001", TEST_GUILD_ID)
    assert fetched is None

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_delete_unit_nonexistent(db_conn, test_server):
    """Test deleting a non-existent unit."""
    success, message = await delete_unit(db_conn, "NONEXISTENT-UNIT", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not found" in message.lower()


@pytest.mark.asyncio
async def test_set_unit_commander_success(db_conn, test_server):
    """Test setting a commander for a unit."""
    # Create characters
    owner_char = Character(
        identifier="unit-owner", name="Unit Owner",
        user_id=100000000000000007, channel_id=900000000000000007,
        guild_id=TEST_GUILD_ID
    )
    await owner_char.upsert(db_conn)
    owner_char = await Character.fetch_by_identifier(db_conn, "unit-owner", TEST_GUILD_ID)

    commander_char = Character(
        identifier="commander", name="Commander",
        user_id=100000000000000008, channel_id=900000000000000008,
        guild_id=TEST_GUILD_ID
    )
    await commander_char.upsert(db_conn)
    commander_char = await Character.fetch_by_identifier(db_conn, "commander", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add both to faction
    member1 = FactionMember(
        faction_id=faction.id, character_id=owner_char.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member1.insert(db_conn)

    member2 = FactionMember(
        faction_id=faction.id, character_id=commander_char.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member2.insert(db_conn)

    # Create wargame config
    wargame_config = WargameConfig(
        guild_id=TEST_GUILD_ID, current_turn=5
    )
    await wargame_config.upsert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # Create territory
    territory = Territory(
        territory_id=1, terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create unit
    unit = Unit(
        unit_id="UNIT-001", name="Test Unit",
        unit_type="infantry",
        owner_character_id=owner_char.id, faction_id=faction.id,
        current_territory_id=1, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit.upsert(db_conn)

    # Set commander
    success, message = await set_unit_commander(db_conn, "UNIT-001", "commander", TEST_GUILD_ID)

    # Verify
    assert success is True
    assert "commander" in message.lower()

    # Verify commander set in database
    fetched = await Unit.fetch_by_unit_id(db_conn, "UNIT-001", TEST_GUILD_ID)
    assert fetched.commander_character_id == commander_char.id
    assert fetched.commander_assigned_turn == 5

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_set_unit_commander_not_in_faction(db_conn, test_server):
    """Test that setting a commander fails if not in same faction."""
    # Create characters
    owner_char = Character(
        identifier="unit-owner", name="Unit Owner",
        user_id=100000000000000009, channel_id=900000000000000009,
        guild_id=TEST_GUILD_ID
    )
    await owner_char.upsert(db_conn)
    owner_char = await Character.fetch_by_identifier(db_conn, "unit-owner", TEST_GUILD_ID)

    commander_char = Character(
        identifier="commander", name="Commander",
        user_id=100000000000000010, channel_id=900000000000000010,
        guild_id=TEST_GUILD_ID
    )
    await commander_char.upsert(db_conn)
    commander_char = await Character.fetch_by_identifier(db_conn, "commander", TEST_GUILD_ID)

    # Create factions
    faction1 = Faction(
        faction_id="faction-1", name="Faction 1",
        guild_id=TEST_GUILD_ID
    )
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "faction-1", TEST_GUILD_ID)

    faction2 = Faction(
        faction_id="faction-2", name="Faction 2",
        guild_id=TEST_GUILD_ID
    )
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "faction-2", TEST_GUILD_ID)

    # Add owner to faction 1
    member1 = FactionMember(
        faction_id=faction1.id, character_id=owner_char.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member1.insert(db_conn)

    # Add commander to faction 2
    member2 = FactionMember(
        faction_id=faction2.id, character_id=commander_char.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member2.insert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # Create territory
    territory = Territory(
        territory_id=1, terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create unit
    unit = Unit(
        unit_id="UNIT-001", name="Test Unit",
        unit_type="infantry",
        owner_character_id=owner_char.id, faction_id=faction1.id,
        current_territory_id=1, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit.upsert(db_conn)

    # Try to set commander from different faction
    success, message = await set_unit_commander(db_conn, "UNIT-001", "commander", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not a member" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_set_unit_commander_nonexistent_unit(db_conn, test_server):
    """Test setting commander on non-existent unit."""
    # Create character
    commander_char = Character(
        identifier="commander", name="Commander",
        user_id=100000000000000011, channel_id=900000000000000011,
        guild_id=TEST_GUILD_ID
    )
    await commander_char.upsert(db_conn)

    # Try to set commander on nonexistent unit
    success, message = await set_unit_commander(db_conn, "NONEXISTENT-UNIT", "commander", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not found" in message.lower()


@pytest.mark.asyncio
async def test_set_unit_commander_nonexistent_character(db_conn, test_server):
    """Test setting invalid character as commander."""
    # Create character
    owner_char = Character(
        identifier="unit-owner", name="Unit Owner",
        user_id=100000000000000012, channel_id=900000000000000012,
        guild_id=TEST_GUILD_ID
    )
    await owner_char.upsert(db_conn)
    owner_char = await Character.fetch_by_identifier(db_conn, "unit-owner", TEST_GUILD_ID)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # Create territory
    territory = Territory(
        territory_id=1, terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create unit
    unit = Unit(
        unit_id="UNIT-001", name="Test Unit",
        unit_type="infantry",
        owner_character_id=owner_char.id,
        current_territory_id=1, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit.upsert(db_conn)

    # Try to set nonexistent character as commander
    success, message = await set_unit_commander(db_conn, "UNIT-001", "nonexistent-commander", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not found" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_unit_guild_isolation(db_conn, test_server_multi_guild):
    """Test that unit operations are properly isolated between guilds."""
    # Create entities with same IDs in both guilds

    # Guild A - Character
    char_a = Character(
        identifier="unit-owner", name="Guild A Owner",
        user_id=100000000000000013, channel_id=900000000000000013,
        guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "unit-owner", TEST_GUILD_ID)

    # Guild B - Character
    char_b = Character(
        identifier="unit-owner", name="Guild B Owner",
        user_id=100000000000000014, channel_id=900000000000000014,
        guild_id=TEST_GUILD_ID_2
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "unit-owner", TEST_GUILD_ID_2)

    # Create unit types in both guilds
    unit_type_a = UnitType(
        type_id="infantry", name="Guild A Infantry",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type_a.upsert(db_conn)

    unit_type_b = UnitType(
        type_id="infantry", name="Guild B Infantry",
        nation=None, guild_id=TEST_GUILD_ID_2,
        movement=3, organization=12, attack=6, defense=6,
        siege_attack=3, siege_defense=4,
        cost_ore=6, cost_lumber=3, cost_coal=1, cost_rations=12, cost_cloth=6,
        upkeep_rations=3, upkeep_cloth=2
    )
    await unit_type_b.upsert(db_conn)

    # Create territories in both guilds
    territory_a = Territory(
        territory_id=1, terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory_a.upsert(db_conn)

    territory_b = Territory(
        territory_id=1, terrain_type="mountain",
        guild_id=TEST_GUILD_ID_2
    )
    await territory_b.upsert(db_conn)

    # Create units with same unit_id in both guilds
    unit_a = Unit(
        unit_id="UNIT-001", name="Guild A Unit",
        unit_type="infantry",
        owner_character_id=char_a.id,
        current_territory_id=1, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit_a.upsert(db_conn)

    unit_b = Unit(
        unit_id="UNIT-001", name="Guild B Unit",
        unit_type="infantry",
        owner_character_id=char_b.id,
        current_territory_id=1, guild_id=TEST_GUILD_ID_2,
        movement=3, organization=12, attack=6, defense=6,
        siege_attack=3, siege_defense=4
    )
    await unit_b.upsert(db_conn)

    # Fetch units for each guild
    fetched_a = await Unit.fetch_by_unit_id(db_conn, "UNIT-001", TEST_GUILD_ID)
    fetched_b = await Unit.fetch_by_unit_id(db_conn, "UNIT-001", TEST_GUILD_ID_2)

    # Verify same unit_id exists independently
    assert fetched_a.unit_id == fetched_b.unit_id == "UNIT-001"

    # But they are different entities
    assert fetched_a.name == "Guild A Unit"
    assert fetched_b.name == "Guild B Unit"
    assert fetched_a.movement != fetched_b.movement
    assert fetched_a.guild_id == TEST_GUILD_ID
    assert fetched_b.guild_id == TEST_GUILD_ID_2

    # Delete unit in guild A
    success_delete_a = await delete_unit(db_conn, "UNIT-001", TEST_GUILD_ID)
    assert success_delete_a[0] is True

    # Verify guild B's unit still exists
    fetched_b_after = await Unit.fetch_by_unit_id(db_conn, "UNIT-001", TEST_GUILD_ID_2)
    assert fetched_b_after is not None
    assert fetched_b_after.name == "Guild B Unit"

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)


@pytest.mark.asyncio
async def test_create_unit_rollback_on_error(db_conn, test_server):
    """Test that create_unit doesn't create partial data on error."""
    # Create character
    char = Character(
        identifier="unit-owner", name="Unit Owner",
        user_id=100000000000000015, channel_id=900000000000000015,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation=None, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # Try to create unit in nonexistent territory (should fail validation)
    success, message = await create_unit(
        db_conn, "UNIT-001", "infantry", "unit-owner", 999, TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()

    # Verify no Unit record created
    fetched = await Unit.fetch_by_unit_id(db_conn, "UNIT-001", TEST_GUILD_ID)
    assert fetched is None

    # Cleanup
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
