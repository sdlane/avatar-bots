"""
Pytest tests for view handlers.
Tests verify view operations for all entity types.

Run with: pytest tests/test_view_handlers.py -v
"""
import pytest
from handlers.view_handlers import (
    view_territory, view_faction, view_unit, view_unit_type,
    view_resources, view_faction_membership, view_units_for_character,
    view_territories_for_character
)
from db import (
    Character, Faction, FactionMember, Territory, TerritoryAdjacency,
    UnitType, Unit, PlayerResources
)
from tests.conftest import TEST_GUILD_ID, TEST_GUILD_ID_2


@pytest.mark.asyncio
async def test_view_territory_success(db_conn, test_server):
    """Test viewing a territory with adjacencies and controller."""
    # Create character
    character = Character(
        identifier="territory-owner", name="Territory Owner",
        channel_id=900000000000000050, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "territory-owner", TEST_GUILD_ID)

    # Create territories
    territory1 = Territory(
        territory_id=1, terrain_type="plains", name="Territory 1",
        controller_character_id=character.id, guild_id=TEST_GUILD_ID
    )
    await territory1.upsert(db_conn)

    territory2 = Territory(
        territory_id=2, terrain_type="mountain", name="Territory 2",
        guild_id=TEST_GUILD_ID
    )
    await territory2.upsert(db_conn)

    # Create adjacency
    adjacency = TerritoryAdjacency(
        territory_a_id=1, territory_b_id=2, guild_id=TEST_GUILD_ID
    )
    await adjacency.upsert(db_conn)

    # View territory
    success, message, data = await view_territory(db_conn, 1, TEST_GUILD_ID)

    # Verify
    assert success is True
    assert data is not None
    assert 'territory' in data
    assert 'adjacent_ids' in data
    assert 'controller_name' in data
    assert data['territory'].territory_id == 1
    assert 2 in data['adjacent_ids']
    assert data['controller_name'] == "Territory Owner"

    # Cleanup
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Character WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_territory_no_controller(db_conn, test_server):
    """Test viewing a territory without a controller."""
    # Create territory
    territory = Territory(
        territory_id=1, terrain_type="plains", name="Uncontrolled Territory",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # View territory
    success, message, data = await view_territory(db_conn, 1, TEST_GUILD_ID)

    # Verify
    assert success is True
    assert data['controller_name'] is None

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_territory_nonexistent(db_conn, test_server):
    """Test viewing a non-existent territory."""
    success, message, data = await view_territory(db_conn, 999, TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not found" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_view_faction_full_details(db_conn, test_server):
    """Test viewing a faction with full details including leader and members."""
    # Create characters
    char1 = Character(
        identifier="leader", name="Leader Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char1.upsert(db_conn)
    char1 = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    char2 = Character(
        identifier="member", name="Member Character",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char2.upsert(db_conn)
    char2 = await Character.fetch_by_identifier(db_conn, "member", TEST_GUILD_ID)

    # Create faction with leader
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID, leader_character_id=char1.id
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add members
    member1 = FactionMember(
        faction_id=faction.id, character_id=char1.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member1.insert(db_conn)

    member2 = FactionMember(
        faction_id=faction.id, character_id=char2.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member2.insert(db_conn)

    # View faction with full details
    success, message, data = await view_faction(db_conn, "test-faction", TEST_GUILD_ID, show_full_details=True)

    # Verify
    assert success is True
    assert data is not None
    assert 'faction' in data
    assert 'leader' in data
    assert 'members' in data
    assert data['faction'].faction_id == "test-faction"
    assert data['leader'].name == "Leader Character"
    assert len(data['members']) == 2

    # Cleanup
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_faction_minimal(db_conn, test_server):
    """Test viewing a faction without full details."""
    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # View faction without full details
    success, message, data = await view_faction(db_conn, "test-faction", TEST_GUILD_ID, show_full_details=False)

    # Verify
    assert success is True
    assert data is not None
    assert 'faction' in data
    assert data['leader'] is None
    assert data['members'] == []

    # Cleanup
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_faction_no_leader(db_conn, test_server):
    """Test viewing a faction without a leader."""
    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # View faction
    success, message, data = await view_faction(db_conn, "test-faction", TEST_GUILD_ID, show_full_details=True)

    # Verify
    assert success is True
    assert data['leader'] is None

    # Cleanup
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_faction_nonexistent(db_conn, test_server):
    """Test viewing a non-existent faction."""
    success, message, data = await view_faction(db_conn, "nonexistent-faction", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not found" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_view_unit_full_details(db_conn, test_server):
    """Test viewing a unit with full details including owner, commander, and faction."""
    # Create character
    char = Character(
        identifier="unit-owner", name="Unit Owner",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "unit-owner", TEST_GUILD_ID)

    commander_char = Character(
        identifier="commander", name="Commander",
        user_id=100000000000000002, channel_id=900000000000000002,
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
        owner_character_id=char.id, faction_id=faction.id,
        commander_character_id=commander_char.id,
        current_territory_id=1, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit.upsert(db_conn)

    # View unit with full details
    success, message, data = await view_unit(db_conn, "UNIT-001", TEST_GUILD_ID, show_full_details=True)

    # Verify
    assert success is True
    assert data is not None
    assert 'unit' in data
    assert 'unit_type' in data
    assert 'owner' in data
    assert 'commander' in data
    assert 'faction' in data
    assert data['unit'].unit_id == "UNIT-001"
    assert data['unit_type'].type_id == "infantry"
    assert data['owner'].name == "Unit Owner"
    assert data['commander'].name == "Commander"
    assert data['faction'].name == "Test Faction"

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_unit_minimal(db_conn, test_server):
    """Test viewing a unit without full details."""
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

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation="fire-nation", guild_id=TEST_GUILD_ID,
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
        owner_character_id=char.id, faction_id=faction.id,
        current_territory_id=1, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit.upsert(db_conn)

    # View unit without full details
    success, message, data = await view_unit(db_conn, "UNIT-001", TEST_GUILD_ID, show_full_details=False)

    # Verify
    assert success is True
    assert data['owner'] is None
    assert data['commander'] is None

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_unit_no_commander(db_conn, test_server):
    """Test viewing a unit without a commander."""
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

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation="fire-nation", guild_id=TEST_GUILD_ID,
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

    # Create unit without commander
    unit = Unit(
        unit_id="UNIT-001", name="Test Unit",
        unit_type="infantry",
        owner_character_id=char.id, faction_id=faction.id,
        current_territory_id=1, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit.upsert(db_conn)

    # View unit
    success, message, data = await view_unit(db_conn, "UNIT-001", TEST_GUILD_ID, show_full_details=True)

    # Verify
    assert success is True
    assert data['commander'] is None

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_unit_nonexistent(db_conn, test_server):
    """Test viewing a non-existent unit."""
    success, message, data = await view_unit(db_conn, "NONEXISTENT-UNIT", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not found" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_view_unit_type_success(db_conn, test_server):
    """Test viewing a unit type."""
    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation="fire-nation", guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # View unit type
    success, message, data = await view_unit_type(db_conn, "infantry", TEST_GUILD_ID)

    # Verify
    assert success is True
    assert data is not None
    assert 'unit_type' in data
    assert data['unit_type'].type_id == "infantry"
    assert data['unit_type'].name == "Infantry Division"

    # Cleanup
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_unit_type_nonexistent(db_conn, test_server):
    """Test viewing a non-existent unit type."""
    success, message, data = await view_unit_type(db_conn, "nonexistent-type", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not found" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_view_resources_success(db_conn, test_server):
    """Test viewing resources by user_id when resources exist."""
    # Create character
    char = Character(
        identifier="resource-char", name="Resource Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "resource-char", TEST_GUILD_ID)

    # Create resources
    resources = PlayerResources(
        character_id=char.id,
        ore=100, lumber=50, coal=200, rations=150, cloth=75, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # View resources
    success, message, data = await view_resources(db_conn, 100000000000000001, TEST_GUILD_ID)

    # Verify
    assert success is True
    assert data is not None
    assert 'character' in data
    assert 'resources' in data
    assert data['character'].name == "Resource Character"
    assert data['resources'].ore == 100


@pytest.mark.asyncio
async def test_view_resources_creates_if_missing(db_conn, test_server):
    """Test that viewing resources creates them if they don't exist."""
    # Create character without resources
    char = Character(
        identifier="no-resource-char", name="No Resource Character",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # View resources
    success, message, data = await view_resources(db_conn, 100000000000000002, TEST_GUILD_ID)

    # Verify
    assert success is True
    assert data is not None
    assert data['resources'].ore == 0
    assert data['resources'].lumber == 0


@pytest.mark.asyncio
async def test_view_resources_nonexistent_character(db_conn, test_server):
    """Test viewing resources for non-existent character."""
    success, message, data = await view_resources(db_conn, 999999999999999999, TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "character" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_view_faction_membership_success(db_conn, test_server):
    """Test viewing faction membership for a character in a faction."""
    # Create characters
    char1 = Character(
        identifier="member-char", name="Member Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char1.upsert(db_conn)
    char1 = await Character.fetch_by_identifier(db_conn, "member-char", TEST_GUILD_ID)

    char2 = Character(
        identifier="leader-char", name="Leader Character",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char2.upsert(db_conn)
    char2 = await Character.fetch_by_identifier(db_conn, "leader-char", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID, leader_character_id=char2.id
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add members
    member1 = FactionMember(
        faction_id=faction.id, character_id=char1.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member1.insert(db_conn)

    member2 = FactionMember(
        faction_id=faction.id, character_id=char2.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member2.insert(db_conn)

    # View faction membership
    success, message, data = await view_faction_membership(db_conn, 100000000000000001, TEST_GUILD_ID)

    # Verify
    assert success is True
    assert data is not None
    assert 'character' in data
    assert 'faction' in data
    assert 'leader' in data
    assert 'members' in data
    assert data['character'].name == "Member Character"
    assert data['faction'].name == "Test Faction"
    assert data['leader'].name == "Leader Character"
    assert len(data['members']) == 2

    # Cleanup
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_faction_membership_not_in_faction(db_conn, test_server):
    """Test viewing faction membership for character not in a faction."""
    # Create character
    char = Character(
        identifier="no-faction-char", name="No Faction Character",
        user_id=100000000000000003, channel_id=900000000000000003,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # View faction membership
    success, message, data = await view_faction_membership(db_conn, 100000000000000003, TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not a member" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_view_units_for_character_owner(db_conn, test_server):
    """Test viewing units for a character who owns units."""
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

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation="fire-nation", guild_id=TEST_GUILD_ID,
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
        owner_character_id=char.id, faction_id=faction.id,
        current_territory_id=1, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit.upsert(db_conn)

    # View units for character
    success, message, data = await view_units_for_character(db_conn, 100000000000000001, TEST_GUILD_ID)

    # Verify
    assert success is True
    assert data is not None
    assert 'character' in data
    assert 'owned_units' in data
    assert 'commanded_units' in data
    assert len(data['owned_units']) == 1
    assert data['owned_units'][0].unit_id == "UNIT-001"

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_units_for_character_commander(db_conn, test_server):
    """Test viewing units for a character who commands units."""
    # Create characters
    owner_char = Character(
        identifier="unit-owner", name="Unit Owner",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await owner_char.upsert(db_conn)
    owner_char = await Character.fetch_by_identifier(db_conn, "unit-owner", TEST_GUILD_ID)

    commander_char = Character(
        identifier="commander", name="Commander",
        user_id=100000000000000002, channel_id=900000000000000002,
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

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation="fire-nation", guild_id=TEST_GUILD_ID,
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

    # Create unit with commander
    unit = Unit(
        unit_id="UNIT-001", name="Test Unit",
        unit_type="infantry",
        owner_character_id=owner_char.id, faction_id=faction.id,
        commander_character_id=commander_char.id,
        current_territory_id=1, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit.upsert(db_conn)

    # View units for commander
    success, message, data = await view_units_for_character(db_conn, 100000000000000002, TEST_GUILD_ID)

    # Verify
    assert success is True
    assert data is not None
    assert len(data['commanded_units']) == 1
    assert data['commanded_units'][0].unit_id == "UNIT-001"

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_units_for_character_both(db_conn, test_server):
    """Test viewing units for a character who both owns and commands units."""
    # Create character
    char = Character(
        identifier="owner-commander", name="Owner Commander",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "owner-commander", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Create unit type
    unit_type = UnitType(
        type_id="infantry", name="Infantry Division",
        nation="fire-nation", guild_id=TEST_GUILD_ID,
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

    # Create owned unit
    unit1 = Unit(
        unit_id="UNIT-001", name="Owned Unit",
        unit_type="infantry",
        owner_character_id=char.id, faction_id=faction.id,
        current_territory_id=1, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit1.upsert(db_conn)

    # Create commanded unit (different owner)
    other_char = Character(
        identifier="other-owner", name="Other Owner",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await other_char.upsert(db_conn)
    other_char = await Character.fetch_by_identifier(db_conn, "other-owner", TEST_GUILD_ID)

    unit2 = Unit(
        unit_id="UNIT-002", name="Commanded Unit",
        unit_type="infantry",
        owner_character_id=other_char.id, faction_id=faction.id,
        commander_character_id=char.id,
        current_territory_id=1, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit2.upsert(db_conn)

    # View units for character
    success, message, data = await view_units_for_character(db_conn, 100000000000000001, TEST_GUILD_ID)

    # Verify
    assert success is True
    assert len(data['owned_units']) == 1
    assert len(data['commanded_units']) == 1
    assert data['owned_units'][0].unit_id == "UNIT-001"
    assert data['commanded_units'][0].unit_id == "UNIT-002"

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_units_for_character_none(db_conn, test_server):
    """Test viewing units for a character with no units."""
    # Create character
    char = Character(
        identifier="no-units-char", name="No Units Character",
        user_id=100000000000000003, channel_id=900000000000000003,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # View units
    success, message, data = await view_units_for_character(db_conn, 100000000000000003, TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "doesn't own or command" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_view_territories_for_character_success(db_conn, test_server):
    """Test viewing territories for a character who controls territories."""
    # Create character
    char = Character(
        identifier="faction-member", name="Faction Member",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "faction-member", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add member
    member = FactionMember(
        faction_id=faction.id, character_id=char.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member.insert(db_conn)

    # Create territories controlled by the character
    territory1 = Territory(
        territory_id=1, terrain_type="plains", name="Territory 1",
        controller_character_id=char.id, guild_id=TEST_GUILD_ID
    )
    await territory1.upsert(db_conn)

    territory2 = Territory(
        territory_id=2, terrain_type="mountain", name="Territory 2",
        controller_character_id=char.id, guild_id=TEST_GUILD_ID
    )
    await territory2.upsert(db_conn)

    # Create adjacency
    adjacency = TerritoryAdjacency(
        territory_a_id=1, territory_b_id=2, guild_id=TEST_GUILD_ID
    )
    await adjacency.upsert(db_conn)

    # View territories
    success, message, data = await view_territories_for_character(db_conn, 100000000000000001, TEST_GUILD_ID)

    # Verify
    assert success is True
    assert data is not None
    assert 'character' in data
    assert 'faction' in data
    assert 'territories' in data
    assert 'adjacencies' in data
    assert len(data['territories']) == 2
    assert 1 in data['adjacencies']
    assert 2 in data['adjacencies'][1]

    # Cleanup
    await db_conn.execute("DELETE FROM TerritoryAdjacency WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_territories_for_character_not_in_faction(db_conn, test_server):
    """Test viewing territories for character who controls no territories."""
    # Create character
    char = Character(
        identifier="no-faction-char", name="No Faction Character",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # View territories (character has no territories)
    success, message, data = await view_territories_for_character(db_conn, 100000000000000002, TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "doesn't control any territories" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_view_territories_for_character_no_territories(db_conn, test_server):
    """Test viewing territories for character who controls no territories (but is in a faction)."""
    # Create character
    char = Character(
        identifier="faction-member", name="Faction Member",
        user_id=100000000000000003, channel_id=900000000000000003,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "faction-member", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add member
    member = FactionMember(
        faction_id=faction.id, character_id=char.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member.insert(db_conn)

    # View territories (character controls no territories even though they're in a faction)
    success, message, data = await view_territories_for_character(db_conn, 100000000000000003, TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "doesn't control any territories" in message.lower()
    assert data is None

    # Cleanup
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_view_handlers_guild_isolation(db_conn, test_server_multi_guild):
    """Test that view operations are properly isolated between guilds."""
    # Create entities with same IDs in both guilds

    # Guild A - Territory
    territory_a = Territory(
        territory_id=1, terrain_type="plains", name="Guild A Territory",
        guild_id=TEST_GUILD_ID
    )
    await territory_a.upsert(db_conn)

    # Guild B - Territory
    territory_b = Territory(
        territory_id=1, terrain_type="mountain", name="Guild B Territory",
        guild_id=TEST_GUILD_ID_2
    )
    await territory_b.upsert(db_conn)

    # Guild A - Faction
    faction_a = Faction(
        faction_id="test-faction", name="Guild A Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction_a.upsert(db_conn)

    # Guild B - Faction
    faction_b = Faction(
        faction_id="test-faction", name="Guild B Faction",
        guild_id=TEST_GUILD_ID_2
    )
    await faction_b.upsert(db_conn)

    # Guild A - Unit Type
    unit_type_a = UnitType(
        type_id="infantry", name="Guild A Infantry",
        nation="fire-nation", guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type_a.upsert(db_conn)

    # Guild B - Unit Type
    unit_type_b = UnitType(
        type_id="infantry", name="Guild B Infantry",
        nation="fire-nation", guild_id=TEST_GUILD_ID_2,
        movement=3, organization=12, attack=6, defense=6,
        siege_attack=3, siege_defense=4,
        cost_ore=6, cost_lumber=3, cost_coal=1, cost_rations=12, cost_cloth=6,
        upkeep_rations=3, upkeep_cloth=2
    )
    await unit_type_b.upsert(db_conn)

    # Guild A - Character with resources
    char_a = Character(
        identifier="shared-char", name="Guild A Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char_a.upsert(db_conn)
    char_a = await Character.fetch_by_identifier(db_conn, "shared-char", TEST_GUILD_ID)

    resources_a = PlayerResources(
        character_id=char_a.id,
        ore=100, lumber=50, coal=25, rations=200, cloth=75, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await resources_a.upsert(db_conn)

    # Guild B - Character with resources
    char_b = Character(
        identifier="shared-char", name="Guild B Character",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID_2
    )
    await char_b.upsert(db_conn)
    char_b = await Character.fetch_by_identifier(db_conn, "shared-char", TEST_GUILD_ID_2)

    resources_b = PlayerResources(
        character_id=char_b.id,
        ore=200, lumber=100, coal=50, rations=300, cloth=150, platinum=0,
        guild_id=TEST_GUILD_ID_2
    )
    await resources_b.upsert(db_conn)

    # View entities for guild A
    territory_a_success, _, territory_a_data = await view_territory(db_conn, 1, TEST_GUILD_ID)
    faction_a_success, _, faction_a_data = await view_faction(db_conn, "test-faction", TEST_GUILD_ID)
    unit_type_a_success, _, unit_type_a_data = await view_unit_type(db_conn, "infantry", TEST_GUILD_ID)
    resources_a_success, _, resources_a_data = await view_resources(db_conn, 100000000000000001, TEST_GUILD_ID)

    # View entities for guild B
    territory_b_success, _, territory_b_data = await view_territory(db_conn, 1, TEST_GUILD_ID_2)
    faction_b_success, _, faction_b_data = await view_faction(db_conn, "test-faction", TEST_GUILD_ID_2)
    unit_type_b_success, _, unit_type_b_data = await view_unit_type(db_conn, "infantry", TEST_GUILD_ID_2)
    resources_b_success, _, resources_b_data = await view_resources(db_conn, 100000000000000002, TEST_GUILD_ID_2)

    # Verify guild A entities
    assert territory_a_success and territory_a_data['territory'].name == "Guild A Territory"
    assert faction_a_success and faction_a_data['faction'].name == "Guild A Faction"
    assert unit_type_a_success and unit_type_a_data['unit_type'].name == "Guild A Infantry"
    assert resources_a_success and resources_a_data['resources'].ore == 100

    # Verify guild B entities
    assert territory_b_success and territory_b_data['territory'].name == "Guild B Territory"
    assert faction_b_success and faction_b_data['faction'].name == "Guild B Faction"
    assert unit_type_b_success and unit_type_b_data['unit_type'].name == "Guild B Infantry"
    assert resources_b_success and resources_b_data['resources'].ore == 200

    # Verify same identifiers exist independently
    assert territory_a_data['territory'].territory_id == territory_b_data['territory'].territory_id == 1
    assert faction_a_data['faction'].faction_id == faction_b_data['faction'].faction_id == "test-faction"
    assert unit_type_a_data['unit_type'].type_id == unit_type_b_data['unit_type'].type_id == "infantry"

    # But they are different entities
    assert territory_a_data['territory'].name != territory_b_data['territory'].name
    assert faction_a_data['faction'].name != faction_b_data['faction'].name
    assert unit_type_a_data['unit_type'].name != unit_type_b_data['unit_type'].name
    assert resources_a_data['resources'].ore != resources_b_data['resources'].ore

    # Cleanup
    await db_conn.execute("DELETE FROM PlayerResources WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
