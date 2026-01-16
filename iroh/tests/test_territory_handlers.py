"""
Unit tests for territory handler functions.
"""
import pytest
import asyncpg
from handlers.territory_handlers import (
    create_territory,
    delete_territory,
    set_territory_controller,
    add_adjacency,
    remove_adjacency
)
from db import Territory, Faction, TerritoryAdjacency, Unit, UnitType, Character, FactionMember
from tests.conftest import TEST_GUILD_ID, TEST_GUILD_ID_2


@pytest.mark.asyncio
async def test_create_territory_success(db_conn, test_server):
    """Test creating a territory with valid terrain type."""
    success, message = await create_territory(
        db_conn, "100", "plains", TEST_GUILD_ID
    )

    assert success is True

    # Verify territory exists
    territory = await Territory.fetch_by_territory_id(db_conn, "100", TEST_GUILD_ID)
    assert territory is not None
    assert territory.territory_id == "100"
    assert territory.terrain_type == "plains"
    assert territory.ore_production == 0


@pytest.mark.asyncio
async def test_create_territory_with_name(db_conn, test_server):
    """Test creating a territory with optional name."""
    success, message = await create_territory(
        db_conn, "101", "mountain", TEST_GUILD_ID, name="Iron Peak"
    )

    assert success is True

    # Verify territory has name
    territory = await Territory.fetch_by_territory_id(db_conn, "101", TEST_GUILD_ID)
    assert territory.name == "Iron Peak"


@pytest.mark.asyncio
async def test_create_territory_duplicate(db_conn, test_server):
    """Test creating a territory with duplicate ID."""
    # Create first territory
    await create_territory(db_conn, "102", "plains", TEST_GUILD_ID)

    # Try to create duplicate
    success, message = await create_territory(
        db_conn, "102", "mountain", TEST_GUILD_ID
    )

    assert success is False


@pytest.mark.asyncio
async def test_create_territory_invalid_terrain(db_conn, test_server):
    """Test creating a territory with invalid terrain type."""
    success, message = await create_territory(
        db_conn, "103", "invalid_terrain", TEST_GUILD_ID
    )

    assert success is False


@pytest.mark.asyncio
async def test_create_territory_valid_terrain_types(db_conn, test_server):
    """Test creating territories with each valid terrain type."""
    valid_terrains = ["plains", "mountain", "desert", "ocean", "lake"]

    for i, terrain in enumerate(valid_terrains):
        success, message = await create_territory(
            db_conn, str(200 + i), terrain, TEST_GUILD_ID
        )
        assert success is True

        territory = await Territory.fetch_by_territory_id(db_conn, str(200 + i), TEST_GUILD_ID)
        assert territory.terrain_type == terrain


@pytest.mark.asyncio
async def test_delete_territory_success(db_conn, test_server):
    """Test deleting a territory with no units."""
    # Create territory
    territory = Territory(
        territory_id="400", terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Delete territory
    success, message = await delete_territory(db_conn, "400", TEST_GUILD_ID)

    assert success is True

    # Verify deleted
    deleted = await Territory.fetch_by_territory_id(db_conn, "400", TEST_GUILD_ID)
    assert deleted is None


@pytest.mark.asyncio
async def test_delete_territory_with_units(db_conn, test_server):
    """Test that deleting a territory with units fails."""
    # Create territory
    territory = Territory(
        territory_id="401", terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create character, faction, and unit type
    char = Character(
        name="Test Char", identifier="test-char", user_id=12345,
        channel_id=999888777, guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "test-char", TEST_GUILD_ID)

    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    unit_type = UnitType(
        type_id="infantry", name="Infantry", nation=None,
        guild_id=TEST_GUILD_ID
    )
    await unit_type.upsert(db_conn)

    # Create unit in territory
    unit = Unit(
        unit_id="UNIT-001", unit_type="infantry",
        owner_character_id=char.id, faction_id=faction.id,
        current_territory_id="401", guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Try to delete territory
    success, message = await delete_territory(db_conn, "401", TEST_GUILD_ID)

    assert success is False


@pytest.mark.asyncio
async def test_set_territory_controller_success(db_conn, test_server):
    """Test assigning character as controller."""
    # Create territory and character
    territory = Territory(
        territory_id="500", terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    character = Character(
        identifier="controller", name="Controller Character",
        channel_id=123, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "controller", TEST_GUILD_ID)

    # Set controller
    success, message = await set_territory_controller(
        db_conn, "500", "controller", TEST_GUILD_ID
    )

    assert success is True

    # Verify controller
    territory = await Territory.fetch_by_territory_id(db_conn, "500", TEST_GUILD_ID)
    assert territory.controller_character_id == character.id


@pytest.mark.asyncio
async def test_set_territory_controller_remove(db_conn, test_server):
    """Test setting controller to 'none'."""
    # Create territory with controller
    character = Character(
        identifier="remover", name="Remove Character",
        channel_id=124, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "remover", TEST_GUILD_ID)

    territory = Territory(
        territory_id="501", terrain_type="plains",
        controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Remove controller
    success, message = await set_territory_controller(
        db_conn, "501", "none", TEST_GUILD_ID
    )

    assert success is True

    # Verify controller removed
    territory = await Territory.fetch_by_territory_id(db_conn, "501", TEST_GUILD_ID)
    assert territory.controller_character_id is None


@pytest.mark.asyncio
async def test_set_territory_controller_nonexistent_faction(db_conn, test_server):
    """Test setting controller to invalid character identifier."""
    # Create territory
    territory = Territory(
        territory_id="502", terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Try to set invalid controller
    success, message = await set_territory_controller(
        db_conn, "502", "nonexistent-character", TEST_GUILD_ID
    )

    assert success is False


@pytest.mark.asyncio
async def test_add_adjacency_success(db_conn, test_server):
    """Test adding adjacency between two territories."""
    # Create territories
    territory1 = Territory(
        territory_id="600", terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory1.upsert(db_conn)

    territory2 = Territory(
        territory_id="601", terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory2.upsert(db_conn)

    # Add adjacency
    success, message = await add_adjacency(
        db_conn, "600", "601", TEST_GUILD_ID
    )

    assert success is True

    # Verify adjacency exists both ways
    adjacent_to_600 = await TerritoryAdjacency.fetch_adjacent(db_conn, "600", TEST_GUILD_ID)
    adjacent_to_601 = await TerritoryAdjacency.fetch_adjacent(db_conn, "601", TEST_GUILD_ID)

    assert "601" in adjacent_to_600
    assert "600" in adjacent_to_601


@pytest.mark.asyncio
async def test_add_adjacency_self(db_conn, test_server):
    """Test that a territory cannot be adjacent to itself."""
    # Create territory
    territory = Territory(
        territory_id="602", terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Try to make territory adjacent to itself
    success, message = await add_adjacency(
        db_conn, "602", "602", TEST_GUILD_ID
    )

    assert success is False


@pytest.mark.asyncio
async def test_add_adjacency_duplicate(db_conn, test_server):
    """Test adding adjacency that already exists returns an error."""
    # Create territories
    territory1 = Territory(
        territory_id="603", terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory1.upsert(db_conn)

    territory2 = Territory(
        territory_id="604", terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory2.upsert(db_conn)

    # Add adjacency first time - should succeed
    success, message = await add_adjacency(
        db_conn, "603", "604", TEST_GUILD_ID
    )
    assert success is True

    # Try to add the same adjacency again - should fail
    success, message = await add_adjacency(
        db_conn, "603", "604", TEST_GUILD_ID
    )

    assert success is False
    assert "already adjacent" in message


@pytest.mark.asyncio
async def test_add_adjacency_nonexistent_territory(db_conn, test_server):
    """Test adding adjacency to non-existent territory."""
    # Create one territory
    territory = Territory(
        territory_id="605", terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Try to add adjacency to non-existent territory
    success, message = await add_adjacency(
        db_conn, "605", "999", TEST_GUILD_ID
    )

    assert success is False


@pytest.mark.asyncio
async def test_remove_adjacency_success(db_conn, test_server):
    """Test removing adjacency."""
    # Create territories with adjacency
    territory1 = Territory(
        territory_id="700", terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory1.upsert(db_conn)

    territory2 = Territory(
        territory_id="701", terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory2.upsert(db_conn)

    adjacency = TerritoryAdjacency(
        territory_a_id="700", territory_b_id="701", guild_id=TEST_GUILD_ID
    )
    await adjacency.upsert(db_conn)

    # Remove adjacency
    success, message = await remove_adjacency(
        db_conn, "700", "701", TEST_GUILD_ID
    )

    assert success is True

    # Verify adjacency removed
    adjacent_to_700 = await TerritoryAdjacency.fetch_adjacent(db_conn, "700", TEST_GUILD_ID)
    adjacent_to_701 = await TerritoryAdjacency.fetch_adjacent(db_conn, "701", TEST_GUILD_ID)

    assert "701" not in adjacent_to_700
    assert "700" not in adjacent_to_701


@pytest.mark.asyncio
async def test_remove_adjacency_nonexistent(db_conn, test_server):
    """Test removing non-existent adjacency."""
    # Create territories without adjacency
    territory1 = Territory(
        territory_id="702", terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory1.upsert(db_conn)

    territory2 = Territory(
        territory_id="703", terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory2.upsert(db_conn)

    # Try to remove non-existent adjacency
    success, message = await remove_adjacency(
        db_conn, "702", "703", TEST_GUILD_ID
    )

    assert success is False


@pytest.mark.asyncio
async def test_territory_guild_isolation(db_conn, test_server_multi_guild):
    """Test that territory operations are properly scoped to guilds."""
    # Create territory with same ID in both guilds
    territory_a = Territory(
        territory_id="1", terrain_type="plains", name="Guild A Territory",
        ore_production=5, guild_id=TEST_GUILD_ID
    )
    await territory_a.upsert(db_conn)

    territory_b = Territory(
        territory_id="1", terrain_type="mountain", name="Guild B Territory",
        ore_production=10, guild_id=TEST_GUILD_ID_2
    )
    await territory_b.upsert(db_conn)

    # Create character in guild A and set as controller
    character_a = Character(
        identifier="test-character", name="Guild A Character",
        channel_id=125, guild_id=TEST_GUILD_ID
    )
    await character_a.upsert(db_conn)
    character_a = await Character.fetch_by_identifier(db_conn, "test-character", TEST_GUILD_ID)

    await set_territory_controller(db_conn, "1", "test-character", TEST_GUILD_ID)

    # Verify guild B's territory is unchanged
    territory_b_check = await Territory.fetch_by_territory_id(db_conn, "1", TEST_GUILD_ID_2)
    assert territory_b_check.name == "Guild B Territory"
    assert territory_b_check.terrain_type == "mountain"
    assert territory_b_check.ore_production == 10
    assert territory_b_check.controller_character_id is None

    # Verify guild A's territory was modified
    territory_a_check = await Territory.fetch_by_territory_id(db_conn, "1", TEST_GUILD_ID)
    assert territory_a_check.controller_character_id == character_a.id

    # Edit territory in guild A directly via model
    territory_a_check.name = "Modified Name"
    territory_a_check.lumber_production = 7
    await territory_a_check.upsert(db_conn)

    # Verify guild B's territory still unchanged
    territory_b_check = await Territory.fetch_by_territory_id(db_conn, "1", TEST_GUILD_ID_2)
    assert territory_b_check.name == "Guild B Territory"
    assert territory_b_check.lumber_production == 0


@pytest.mark.asyncio
async def test_add_adjacency_rollback_on_error(db_conn, test_server):
    """Test that adjacency creation fails cleanly with invalid territory."""
    # Create one valid territory
    territory1 = Territory(
        territory_id="800", terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory1.upsert(db_conn)

    # Try to create adjacency with invalid territory
    success, message = await add_adjacency(
        db_conn, "800", "999", TEST_GUILD_ID
    )

    assert success is False

    # Verify no adjacency was created
    adjacent = await TerritoryAdjacency.fetch_adjacent(db_conn, "800", TEST_GUILD_ID)
    assert len(adjacent) == 0
