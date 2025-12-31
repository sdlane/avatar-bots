"""
Pytest tests for list handlers.
Tests verify list operations for all entity types.

Run with: pytest tests/test_list_handlers.py -v
"""
import pytest
from handlers.list_handlers import list_factions, list_territories, list_unit_types, list_units
from db import (
    Character, Faction, FactionMember, Territory, UnitType, Unit, WargameConfig
)
from tests.conftest import TEST_GUILD_ID, TEST_GUILD_ID_2


@pytest.mark.asyncio
async def test_list_factions_success(db_conn, test_server):
    """Test listing factions with member counts."""
    # Create characters
    char1 = Character(
        identifier="char1", name="Character 1",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char1.upsert(db_conn)
    char1 = await Character.fetch_by_identifier(db_conn, "char1", TEST_GUILD_ID)

    char2 = Character(
        identifier="char2", name="Character 2",
        user_id=100000000000000002, channel_id=900000000000000002,
        guild_id=TEST_GUILD_ID
    )
    await char2.upsert(db_conn)
    char2 = await Character.fetch_by_identifier(db_conn, "char2", TEST_GUILD_ID)

    # Create factions
    faction1 = Faction(
        faction_id="faction-1", name="Faction One",
        guild_id=TEST_GUILD_ID, leader_character_id=char1.id
    )
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "faction-1", TEST_GUILD_ID)

    faction2 = Faction(
        faction_id="faction-2", name="Faction Two",
        guild_id=TEST_GUILD_ID
    )
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "faction-2", TEST_GUILD_ID)

    # Add members
    member1 = FactionMember(
        faction_id=faction1.id, character_id=char1.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member1.insert(db_conn)

    member2 = FactionMember(
        faction_id=faction1.id, character_id=char2.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member2.insert(db_conn)

    # List factions
    success, message, data = await list_factions(db_conn, TEST_GUILD_ID)

    # Verify
    assert success is True
    assert data is not None
    assert len(data) == 2
    assert all('faction' in item and 'member_count' in item for item in data)

    # Find faction1 and verify member count
    faction1_data = next(item for item in data if item['faction'].faction_id == "faction-1")
    assert faction1_data['member_count'] == 2

    faction2_data = next(item for item in data if item['faction'].faction_id == "faction-2")
    assert faction2_data['member_count'] == 0

    # Cleanup
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_list_factions_empty(db_conn, test_server):
    """Test listing factions when none exist."""
    success, message, data = await list_factions(db_conn, TEST_GUILD_ID)

    # Verify returns False for empty
    assert success is False
    assert "no factions found" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_list_territories_success(db_conn, test_server):
    """Test listing territories with controllers."""
    # Create faction
    faction = Faction(
        faction_id="territory-faction", name="Territory Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "territory-faction", TEST_GUILD_ID)

    # Create territories
    territory1 = Territory(
        territory_id=1, terrain_type="plains", name="Territory 1",
        controller_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await territory1.upsert(db_conn)

    territory2 = Territory(
        territory_id=2, terrain_type="mountain", name="Territory 2",
        controller_faction_id=None, guild_id=TEST_GUILD_ID
    )
    await territory2.upsert(db_conn)

    # List territories
    success, message, data = await list_territories(db_conn, TEST_GUILD_ID)

    # Verify
    assert success is True
    assert data is not None
    assert len(data) == 2
    assert all('territory' in item and 'controller_name' in item for item in data)

    # Verify controller names
    terr1_data = next(item for item in data if item['territory'].territory_id == 1)
    assert terr1_data['controller_name'] == "Territory Faction"

    terr2_data = next(item for item in data if item['territory'].territory_id == 2)
    assert terr2_data['controller_name'] == "Uncontrolled"

    # Cleanup
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_list_territories_empty(db_conn, test_server):
    """Test listing territories when none exist."""
    success, message, data = await list_territories(db_conn, TEST_GUILD_ID)

    # Verify returns False for empty
    assert success is False
    assert "no territories found" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_list_unit_types_success(db_conn, test_server):
    """Test listing unit types."""
    # Create unit types
    unit_type1 = UnitType(
        type_id="infantry", name="Infantry Division",
        nation="fire-nation", guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type1.upsert(db_conn)

    unit_type2 = UnitType(
        type_id="cavalry", name="Cavalry Division",
        nation="earth-kingdom", guild_id=TEST_GUILD_ID,
        movement=4, organization=8, attack=7, defense=3,
        siege_attack=1, siege_defense=2,
        cost_ore=3, cost_lumber=5, cost_coal=0, cost_rations=15, cost_cloth=8,
        upkeep_rations=3, upkeep_cloth=2
    )
    await unit_type2.upsert(db_conn)

    # List unit types
    success, message, data = await list_unit_types(db_conn, TEST_GUILD_ID)

    # Verify
    assert success is True
    assert data is not None
    assert len(data) == 2
    assert all(isinstance(item, UnitType) for item in data)

    # Verify unit types
    type_ids = [ut.type_id for ut in data]
    assert "infantry" in type_ids
    assert "cavalry" in type_ids

    # Cleanup
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_list_unit_types_empty(db_conn, test_server):
    """Test listing unit types when none exist."""
    success, message, data = await list_unit_types(db_conn, TEST_GUILD_ID)

    # Verify returns False for empty
    assert success is False
    assert "no unit types found" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_list_units_success(db_conn, test_server):
    """Test listing units with owner and faction names."""
    # Create character
    char = Character(
        identifier="unit-owner", name="Unit Owner",
        user_id=100000000000000003, channel_id=900000000000000003,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "unit-owner", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="unit-faction", name="Unit Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "unit-faction", TEST_GUILD_ID)

    # Create unit type
    unit_type = UnitType(
        type_id="test-unit", name="Test Unit",
        nation="test-nation", guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type.upsert(db_conn)

    # Create territory
    territory = Territory(
        territory_id=10, terrain_type="plains",
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create unit
    unit = Unit(
        unit_id="TEST-001", name="Test Unit 1",
        unit_type="test-unit",
        owner_character_id=char.id, faction_id=faction.id,
        current_territory_id=10, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit.upsert(db_conn)

    # List units
    success, message, data = await list_units(db_conn, TEST_GUILD_ID)

    # Verify
    assert success is True
    assert data is not None
    assert len(data) == 1
    assert 'unit' in data[0]
    assert 'owner_name' in data[0]
    assert 'faction_name' in data[0]
    assert data[0]['owner_name'] == "Unit Owner"
    assert data[0]['faction_name'] == "Unit Faction"

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_list_units_empty(db_conn, test_server):
    """Test listing units when none exist."""
    success, message, data = await list_units(db_conn, TEST_GUILD_ID)

    # Verify returns False for empty
    assert success is False
    assert "no units found" in message.lower()
    assert data is None


@pytest.mark.asyncio
async def test_list_handlers_guild_isolation(db_conn, test_server_multi_guild):
    """Test that list operations are properly isolated between guilds."""
    # Create entities with same identifiers in both guilds

    # Guild A - Faction
    faction_a = Faction(
        faction_id="shared-faction", name="Guild A Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction_a.upsert(db_conn)

    # Guild B - Faction
    faction_b = Faction(
        faction_id="shared-faction", name="Guild B Faction",
        guild_id=TEST_GUILD_ID_2
    )
    await faction_b.upsert(db_conn)

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

    # Guild A - Unit Type
    unit_type_a = UnitType(
        type_id="infantry", name="Guild A Infantry",
        nation="nation-a", guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3,
        cost_ore=5, cost_lumber=2, cost_coal=0, cost_rations=10, cost_cloth=5,
        upkeep_rations=2, upkeep_cloth=1
    )
    await unit_type_a.upsert(db_conn)

    # Guild B - Unit Type
    unit_type_b = UnitType(
        type_id="infantry", name="Guild B Infantry",
        nation="nation-b", guild_id=TEST_GUILD_ID_2,
        movement=3, organization=12, attack=6, defense=6,
        siege_attack=3, siege_defense=4,
        cost_ore=6, cost_lumber=3, cost_coal=1, cost_rations=12, cost_cloth=6,
        upkeep_rations=3, upkeep_cloth=2
    )
    await unit_type_b.upsert(db_conn)

    # List entities for guild A
    factions_a_success, _, factions_a = await list_factions(db_conn, TEST_GUILD_ID)
    territories_a_success, _, territories_a = await list_territories(db_conn, TEST_GUILD_ID)
    unit_types_a_success, _, unit_types_a = await list_unit_types(db_conn, TEST_GUILD_ID)

    # List entities for guild B
    factions_b_success, _, factions_b = await list_factions(db_conn, TEST_GUILD_ID_2)
    territories_b_success, _, territories_b = await list_territories(db_conn, TEST_GUILD_ID_2)
    unit_types_b_success, _, unit_types_b = await list_unit_types(db_conn, TEST_GUILD_ID_2)

    # Verify each list contains only entities from the requested guild
    assert factions_a_success and len(factions_a) == 1
    assert factions_a[0]['faction'].name == "Guild A Faction"
    assert factions_a[0]['faction'].guild_id == TEST_GUILD_ID

    assert factions_b_success and len(factions_b) == 1
    assert factions_b[0]['faction'].name == "Guild B Faction"
    assert factions_b[0]['faction'].guild_id == TEST_GUILD_ID_2

    assert territories_a_success and len(territories_a) == 1
    assert territories_a[0]['territory'].name == "Guild A Territory"
    assert territories_a[0]['territory'].guild_id == TEST_GUILD_ID

    assert territories_b_success and len(territories_b) == 1
    assert territories_b[0]['territory'].name == "Guild B Territory"
    assert territories_b[0]['territory'].guild_id == TEST_GUILD_ID_2

    assert unit_types_a_success and len(unit_types_a) == 1
    assert unit_types_a[0].name == "Guild A Infantry"
    assert unit_types_a[0].guild_id == TEST_GUILD_ID

    assert unit_types_b_success and len(unit_types_b) == 1
    assert unit_types_b[0].name == "Guild B Infantry"
    assert unit_types_b[0].guild_id == TEST_GUILD_ID_2

    # Verify same identifiers exist independently in both guilds
    assert factions_a[0]['faction'].faction_id == factions_b[0]['faction'].faction_id == "shared-faction"
    assert territories_a[0]['territory'].territory_id == territories_b[0]['territory'].territory_id == 1
    assert unit_types_a[0].type_id == unit_types_b[0].type_id == "infantry"

    # But they are different entities
    assert factions_a[0]['faction'].name != factions_b[0]['faction'].name
    assert territories_a[0]['territory'].name != territories_b[0]['territory'].name
    assert unit_types_a[0].name != unit_types_b[0].name

    # Cleanup
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)
