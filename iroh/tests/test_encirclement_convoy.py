"""
Pytest tests for convoy support in the encirclement phase.
Tests naval convoy and aerial convoy functionality for preventing encirclement.

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_encirclement_convoy.py -v
"""
import pytest
from datetime import datetime
from handlers.turn_handlers import execute_encirclement_phase
from handlers.encirclement_handlers import (
    get_naval_convoy_territories,
    get_aerial_convoy_territories,
    get_convoy_traversable_territories,
    bfs_can_reach_friendly,
    check_unit_encircled,
    unit_has_keyword,
)
from handlers.order_handlers import submit_unit_order
from db import (
    Character, Unit, Territory, TerritoryAdjacency, Faction, Order,
    FactionMember
)
from order_types import OrderType, ORDER_PHASE_MAP, ORDER_PRIORITY_MAP, OrderStatus
from tests.conftest import TEST_GUILD_ID


# =============================================================================
# Helper function tests
# =============================================================================

def test_unit_has_keyword_present():
    """Test unit_has_keyword returns True when keyword is present."""
    unit = Unit(
        unit_id="test-unit", name="Test Unit", unit_type="infantry",
        keywords=['aerial-transport', 'flying'], guild_id=TEST_GUILD_ID
    )
    assert unit_has_keyword(unit, 'aerial-transport') is True


def test_unit_has_keyword_absent():
    """Test unit_has_keyword returns False when keyword is absent."""
    unit = Unit(
        unit_id="test-unit", name="Test Unit", unit_type="infantry",
        keywords=['flying'], guild_id=TEST_GUILD_ID
    )
    assert unit_has_keyword(unit, 'aerial-transport') is False


def test_unit_has_keyword_no_keywords():
    """Test unit_has_keyword returns False when keywords is None."""
    unit = Unit(
        unit_id="test-unit", name="Test Unit", unit_type="infantry",
        keywords=None, guild_id=TEST_GUILD_ID
    )
    assert unit_has_keyword(unit, 'aerial-transport') is False


# =============================================================================
# Naval convoy tests
# =============================================================================

@pytest.mark.asyncio
async def test_naval_convoy_provides_traversable_ocean(db_conn, test_server):
    """Test that naval convoy makes ocean territory traversable."""
    # Create faction
    faction = Faction(faction_id="water-tribe", name="Water Tribe", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "water-tribe", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="captain", name="Captain",
        channel_id=999000000000000010,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "captain", TEST_GUILD_ID)

    # Create ocean territory
    ocean = Territory(
        territory_id="ocean-convoy", name="Ocean Convoy",
        terrain_type="ocean", guild_id=TEST_GUILD_ID
    )
    await ocean.upsert(db_conn)

    # Create naval unit in ocean with naval_convoy order
    naval_unit = Unit(
        unit_id="ship-convoy", name="Convoy Ship", unit_type="ship",
        owner_character_id=character.id,
        is_naval=True,
        current_territory_id="ocean-convoy",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await naval_unit.upsert(db_conn)
    naval_unit = await Unit.fetch_by_unit_id(db_conn, "ship-convoy", TEST_GUILD_ID)

    # Create naval_convoy order
    order = Order(
        order_id="ORD-CONV-01",
        order_type=OrderType.UNIT.value,
        unit_ids=[naval_unit.id],
        character_id=character.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.UNIT].value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.ONGOING.value,
        order_data={'action': 'naval_convoy', 'path': ['ocean-convoy']},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    allied_ids = {faction.id}

    # Get naval convoy territories
    convoy_territories = await get_naval_convoy_territories(db_conn, TEST_GUILD_ID, allied_ids)

    assert "ocean-convoy" in convoy_territories


@pytest.mark.asyncio
async def test_naval_convoy_requires_active_order(db_conn, test_server):
    """Test that naval convoy requires PENDING/ONGOING order."""
    # Create faction
    faction = Faction(faction_id="water-tribe", name="Water Tribe", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "water-tribe", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="captain", name="Captain",
        channel_id=999000000000000011,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "captain", TEST_GUILD_ID)

    # Create ocean territory
    ocean = Territory(
        territory_id="ocean-no-order", name="Ocean No Order",
        terrain_type="ocean", guild_id=TEST_GUILD_ID
    )
    await ocean.upsert(db_conn)

    # Create naval unit in ocean WITHOUT convoy order
    naval_unit = Unit(
        unit_id="ship-no-convoy", name="No Convoy Ship", unit_type="ship",
        owner_character_id=character.id,
        is_naval=True,
        current_territory_id="ocean-no-order",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await naval_unit.upsert(db_conn)

    allied_ids = {faction.id}

    # Get naval convoy territories (should be empty)
    convoy_territories = await get_naval_convoy_territories(db_conn, TEST_GUILD_ID, allied_ids)

    assert "ocean-no-order" not in convoy_territories


@pytest.mark.asyncio
async def test_enemy_naval_convoy_not_usable(db_conn, test_server):
    """Test that enemy naval convoy does not provide traversable path."""
    # Create two factions
    faction1 = Faction(faction_id="water-tribe", name="Water Tribe", guild_id=TEST_GUILD_ID)
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "water-tribe", TEST_GUILD_ID)

    faction2 = Faction(faction_id="fire-nation", name="Fire Nation", guild_id=TEST_GUILD_ID)
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "fire-nation", TEST_GUILD_ID)

    # Create character for enemy faction
    enemy_captain = Character(
        identifier="enemy-captain", name="Enemy Captain",
        channel_id=999000000000000012,
        represented_faction_id=faction2.id, guild_id=TEST_GUILD_ID
    )
    await enemy_captain.upsert(db_conn)
    enemy_captain = await Character.fetch_by_identifier(db_conn, "enemy-captain", TEST_GUILD_ID)

    # Create ocean territory
    ocean = Territory(
        territory_id="enemy-ocean", name="Enemy Ocean",
        terrain_type="ocean", guild_id=TEST_GUILD_ID
    )
    await ocean.upsert(db_conn)

    # Create enemy naval unit with convoy order
    enemy_ship = Unit(
        unit_id="enemy-ship", name="Enemy Ship", unit_type="ship",
        owner_character_id=enemy_captain.id,
        is_naval=True,
        current_territory_id="enemy-ocean",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await enemy_ship.upsert(db_conn)
    enemy_ship = await Unit.fetch_by_unit_id(db_conn, "enemy-ship", TEST_GUILD_ID)

    # Create naval_convoy order for enemy
    order = Order(
        order_id="ORD-ENEMY-CONV",
        order_type=OrderType.UNIT.value,
        unit_ids=[enemy_ship.id],
        character_id=enemy_captain.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.UNIT].value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.ONGOING.value,
        order_data={'action': 'naval_convoy', 'path': ['enemy-ocean']},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    # Allied IDs for faction1 (not faction2)
    allied_ids = {faction1.id}

    # Get naval convoy territories (should NOT include enemy convoy)
    convoy_territories = await get_naval_convoy_territories(db_conn, TEST_GUILD_ID, allied_ids)

    assert "enemy-ocean" not in convoy_territories


@pytest.mark.asyncio
async def test_naval_convoy_prevents_encirclement(db_conn, test_server):
    """Test that unit on island is NOT encircled when naval convoy provides path."""
    # Create faction
    faction = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="island-soldier", name="Island Soldier",
        channel_id=999000000000000013,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "island-soldier", TEST_GUILD_ID)

    # Create territories: island -> ocean -> mainland (friendly)
    island = Territory(
        territory_id="remote-island", name="Remote Island",
        terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await island.upsert(db_conn)

    ocean = Territory(
        territory_id="convoy-ocean", name="Convoy Ocean",
        terrain_type="ocean", guild_id=TEST_GUILD_ID
    )
    await ocean.upsert(db_conn)

    mainland = Territory(
        territory_id="mainland", name="Mainland",
        terrain_type="plains", controller_faction_id=faction.id,
        guild_id=TEST_GUILD_ID
    )
    await mainland.upsert(db_conn)

    # Create adjacencies
    adj1 = TerritoryAdjacency(territory_a_id="convoy-ocean", territory_b_id="remote-island", guild_id=TEST_GUILD_ID)
    await adj1.upsert(db_conn)

    adj2 = TerritoryAdjacency(territory_a_id="convoy-ocean", territory_b_id="mainland", guild_id=TEST_GUILD_ID)
    await adj2.upsert(db_conn)

    # Create naval unit with convoy order
    naval_unit = Unit(
        unit_id="convoy-ship", name="Convoy Ship", unit_type="ship",
        owner_character_id=character.id,
        is_naval=True,
        current_territory_id="convoy-ocean",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await naval_unit.upsert(db_conn)
    naval_unit = await Unit.fetch_by_unit_id(db_conn, "convoy-ship", TEST_GUILD_ID)

    convoy_order = Order(
        order_id="ORD-CONVOY-SAVE",
        order_type=OrderType.UNIT.value,
        unit_ids=[naval_unit.id],
        character_id=character.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.UNIT].value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.ONGOING.value,
        order_data={'action': 'naval_convoy', 'path': ['convoy-ocean']},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await convoy_order.upsert(db_conn)

    # Create land unit on island
    land_unit = Unit(
        unit_id="island-unit", name="Island Unit", unit_type="infantry",
        owner_character_id=character.id,
        is_naval=False,
        current_territory_id="remote-island",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await land_unit.upsert(db_conn)
    land_unit = await Unit.fetch_by_unit_id(db_conn, "island-unit", TEST_GUILD_ID)

    # Check encirclement - should NOT be encircled due to convoy
    is_encircled = await check_unit_encircled(db_conn, land_unit, TEST_GUILD_ID)

    assert is_encircled is False


# =============================================================================
# Aerial convoy tests
# =============================================================================

@pytest.mark.asyncio
async def test_aerial_convoy_provides_traversable_territory(db_conn, test_server):
    """Test that aerial convoy makes territory traversable."""
    # Create faction
    faction = Faction(faction_id="air-nomads", name="Air Nomads", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "air-nomads", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="air-captain", name="Air Captain",
        channel_id=999000000000000014,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "air-captain", TEST_GUILD_ID)

    # Create neutral territory
    neutral = Territory(
        territory_id="neutral-sky", name="Neutral Sky",
        terrain_type="plains", guild_id=TEST_GUILD_ID  # uncontrolled
    )
    await neutral.upsert(db_conn)

    # Create aerial unit with aerial-transport keyword and aerial_convoy order
    aerial_unit = Unit(
        unit_id="sky-bison", name="Sky Bison", unit_type="aerial",
        owner_character_id=character.id,
        is_naval=False,
        keywords=['aerial-transport', 'flying'],
        current_territory_id="neutral-sky",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await aerial_unit.upsert(db_conn)
    aerial_unit = await Unit.fetch_by_unit_id(db_conn, "sky-bison", TEST_GUILD_ID)

    # Create aerial_convoy order
    order = Order(
        order_id="ORD-AIR-CONV-01",
        order_type=OrderType.UNIT.value,
        unit_ids=[aerial_unit.id],
        character_id=character.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.UNIT].value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.ONGOING.value,
        order_data={'action': 'aerial_convoy', 'path': ['neutral-sky']},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    allied_ids = {faction.id}
    enemy_ids = set()

    # Get aerial convoy territories
    convoy_territories = await get_aerial_convoy_territories(db_conn, TEST_GUILD_ID, allied_ids, enemy_ids)

    assert "neutral-sky" in convoy_territories


@pytest.mark.asyncio
async def test_aerial_convoy_not_in_enemy_territory(db_conn, test_server):
    """Test that aerial convoy does NOT work in enemy-controlled territory."""
    # Create two factions at war
    faction1 = Faction(faction_id="air-nomads", name="Air Nomads", guild_id=TEST_GUILD_ID)
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "air-nomads", TEST_GUILD_ID)

    faction2 = Faction(faction_id="fire-nation", name="Fire Nation", guild_id=TEST_GUILD_ID)
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "fire-nation", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="air-pilot", name="Air Pilot",
        channel_id=999000000000000015,
        represented_faction_id=faction1.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "air-pilot", TEST_GUILD_ID)

    # Create enemy-controlled territory
    enemy_territory = Territory(
        territory_id="enemy-airspace", name="Enemy Airspace",
        terrain_type="plains", controller_faction_id=faction2.id,
        guild_id=TEST_GUILD_ID
    )
    await enemy_territory.upsert(db_conn)

    # Create aerial unit with aerial-transport keyword
    aerial_unit = Unit(
        unit_id="bison-in-enemy", name="Bison In Enemy", unit_type="aerial",
        owner_character_id=character.id,
        is_naval=False,
        keywords=['aerial-transport'],
        current_territory_id="enemy-airspace",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await aerial_unit.upsert(db_conn)
    aerial_unit = await Unit.fetch_by_unit_id(db_conn, "bison-in-enemy", TEST_GUILD_ID)

    # Create aerial_convoy order
    order = Order(
        order_id="ORD-AIR-ENEMY",
        order_type=OrderType.UNIT.value,
        unit_ids=[aerial_unit.id],
        character_id=character.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.UNIT].value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.ONGOING.value,
        order_data={'action': 'aerial_convoy', 'path': ['enemy-airspace']},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    allied_ids = {faction1.id}
    enemy_ids = {faction2.id}

    # Get aerial convoy territories (should NOT include enemy territory)
    convoy_territories = await get_aerial_convoy_territories(db_conn, TEST_GUILD_ID, allied_ids, enemy_ids)

    assert "enemy-airspace" not in convoy_territories


@pytest.mark.asyncio
async def test_aerial_convoy_requires_keyword(db_conn, test_server):
    """Test that aerial convoy requires aerial-transport keyword."""
    # Create faction
    faction = Faction(faction_id="air-nomads", name="Air Nomads", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "air-nomads", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="no-keyword-pilot", name="No Keyword Pilot",
        channel_id=999000000000000016,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "no-keyword-pilot", TEST_GUILD_ID)

    # Create territory
    territory = Territory(
        territory_id="no-keyword-sky", name="No Keyword Sky",
        terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create unit WITHOUT aerial-transport keyword
    unit = Unit(
        unit_id="no-keyword-unit", name="No Keyword Unit", unit_type="infantry",
        owner_character_id=character.id,
        is_naval=False,
        keywords=['flying'],  # has flying but NOT aerial-transport
        current_territory_id="no-keyword-sky",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "no-keyword-unit", TEST_GUILD_ID)

    # Create aerial_convoy order
    order = Order(
        order_id="ORD-NO-KEYWORD",
        order_type=OrderType.UNIT.value,
        unit_ids=[unit.id],
        character_id=character.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.UNIT].value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.ONGOING.value,
        order_data={'action': 'aerial_convoy', 'path': ['no-keyword-sky']},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await order.upsert(db_conn)

    allied_ids = {faction.id}
    enemy_ids = set()

    # Get aerial convoy territories (should NOT include territory)
    convoy_territories = await get_aerial_convoy_territories(db_conn, TEST_GUILD_ID, allied_ids, enemy_ids)

    assert "no-keyword-sky" not in convoy_territories


@pytest.mark.asyncio
async def test_aerial_convoy_bridges_water(db_conn, test_server):
    """Test that aerial convoy can bridge water territory."""
    # Create faction
    faction = Faction(faction_id="air-nomads", name="Air Nomads", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "air-nomads", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="water-crosser", name="Water Crosser",
        channel_id=999000000000000017,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "water-crosser", TEST_GUILD_ID)

    # Create territories: island -> water (aerial convoy) -> mainland
    island = Territory(
        territory_id="air-island", name="Air Island",
        terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await island.upsert(db_conn)

    water = Territory(
        territory_id="bridged-water", name="Bridged Water",
        terrain_type="ocean", guild_id=TEST_GUILD_ID
    )
    await water.upsert(db_conn)

    mainland = Territory(
        territory_id="air-mainland", name="Air Mainland",
        terrain_type="plains", controller_faction_id=faction.id,
        guild_id=TEST_GUILD_ID
    )
    await mainland.upsert(db_conn)

    # Create adjacencies
    adj1 = TerritoryAdjacency(territory_a_id="air-island", territory_b_id="bridged-water", guild_id=TEST_GUILD_ID)
    await adj1.upsert(db_conn)

    adj2 = TerritoryAdjacency(territory_a_id="air-mainland", territory_b_id="bridged-water", guild_id=TEST_GUILD_ID)
    await adj2.upsert(db_conn)

    # Create aerial unit with convoy order over water
    aerial_unit = Unit(
        unit_id="water-bison", name="Water Bison", unit_type="aerial",
        owner_character_id=character.id,
        is_naval=False,
        keywords=['aerial-transport'],
        current_territory_id="bridged-water",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await aerial_unit.upsert(db_conn)
    aerial_unit = await Unit.fetch_by_unit_id(db_conn, "water-bison", TEST_GUILD_ID)

    convoy_order = Order(
        order_id="ORD-AIR-WATER",
        order_type=OrderType.UNIT.value,
        unit_ids=[aerial_unit.id],
        character_id=character.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.UNIT].value,
        priority=ORDER_PRIORITY_MAP[OrderType.UNIT],
        status=OrderStatus.ONGOING.value,
        order_data={'action': 'aerial_convoy', 'path': ['bridged-water']},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await convoy_order.upsert(db_conn)

    # Create land unit on island
    land_unit = Unit(
        unit_id="air-stranded", name="Air Stranded", unit_type="infantry",
        owner_character_id=character.id,
        is_naval=False,
        current_territory_id="air-island",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await land_unit.upsert(db_conn)
    land_unit = await Unit.fetch_by_unit_id(db_conn, "air-stranded", TEST_GUILD_ID)

    # Check encirclement - should NOT be encircled due to aerial convoy
    is_encircled = await check_unit_encircled(db_conn, land_unit, TEST_GUILD_ID)

    assert is_encircled is False


# =============================================================================
# Order validation tests
# =============================================================================

@pytest.mark.asyncio
async def test_aerial_convoy_order_rejected_without_keyword(db_conn, test_server):
    """Test that aerial_convoy order is rejected for units without keyword."""
    # Create faction
    faction = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="no-fly", name="No Fly",
        channel_id=999000000000000018,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "no-fly", TEST_GUILD_ID)

    # Add faction member
    member = FactionMember(
        faction_id=faction.id, character_id=character.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member.upsert(db_conn)

    # Create territories and adjacency
    territory1 = Territory(
        territory_id="ground-base-1", name="Ground Base 1",
        terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory1.upsert(db_conn)

    territory2 = Territory(
        territory_id="ground-base-2", name="Ground Base 2",
        terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory2.upsert(db_conn)

    adj = TerritoryAdjacency(territory_a_id="ground-base-1", territory_b_id="ground-base-2", guild_id=TEST_GUILD_ID)
    await adj.upsert(db_conn)

    # Create unit WITHOUT aerial-transport keyword
    unit = Unit(
        unit_id="ground-unit", name="Ground Unit", unit_type="infantry",
        owner_character_id=character.id,
        is_naval=False,
        keywords=None,  # no keywords
        current_territory_id="ground-base-1",
        organization=10, max_organization=10,
        movement=2,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Set up WargameConfig for current turn
    await db_conn.execute("""
        INSERT INTO WargameConfig (guild_id, current_turn)
        VALUES ($1, 1)
        ON CONFLICT (guild_id) DO UPDATE SET current_turn = 1;
    """, TEST_GUILD_ID)

    # Try to submit aerial_convoy order (should fail)
    success, message, extra = await submit_unit_order(
        db_conn, ['ground-unit'], 'aerial_convoy', ['ground-base-1', 'ground-base-2'],
        TEST_GUILD_ID, character.id
    )

    assert success is False
    assert "aerial-transport" in message.lower()


@pytest.mark.asyncio
async def test_aerial_convoy_order_accepted_with_keyword(db_conn, test_server):
    """Test that aerial_convoy order is accepted for units with keyword."""
    # Create faction
    faction = Faction(faction_id="air-nomads", name="Air Nomads", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "air-nomads", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="can-fly", name="Can Fly",
        channel_id=999000000000000019,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "can-fly", TEST_GUILD_ID)

    # Add faction member
    member = FactionMember(
        faction_id=faction.id, character_id=character.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member.upsert(db_conn)

    # Create territories and adjacency
    territory1 = Territory(
        territory_id="sky-base", name="Sky Base",
        terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory1.upsert(db_conn)

    territory2 = Territory(
        territory_id="sky-dest", name="Sky Dest",
        terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory2.upsert(db_conn)

    adj = TerritoryAdjacency(territory_a_id="sky-base", territory_b_id="sky-dest", guild_id=TEST_GUILD_ID)
    await adj.upsert(db_conn)

    # Create unit WITH aerial-transport keyword
    unit = Unit(
        unit_id="flying-unit", name="Flying Unit", unit_type="aerial",
        owner_character_id=character.id,
        is_naval=False,
        keywords=['aerial-transport'],
        current_territory_id="sky-base",
        organization=10, max_organization=10,
        movement=2,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Set up WargameConfig for current turn
    await db_conn.execute("""
        INSERT INTO WargameConfig (guild_id, current_turn)
        VALUES ($1, 1)
        ON CONFLICT (guild_id) DO UPDATE SET current_turn = 1;
    """, TEST_GUILD_ID)

    # Submit aerial_convoy order (should succeed)
    success, message, extra = await submit_unit_order(
        db_conn, ['flying-unit'], 'aerial_convoy', ['sky-base', 'sky-dest'],
        TEST_GUILD_ID, character.id
    )

    assert success is True


# =============================================================================
# Combined convoy tests
# =============================================================================

@pytest.mark.asyncio
async def test_combined_naval_and_aerial_convoy(db_conn, test_server):
    """Test that both naval and aerial convoy provide traversable paths."""
    # Create faction
    faction = Faction(faction_id="combined-faction", name="Combined Faction", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "combined-faction", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="combined-commander", name="Combined Commander",
        channel_id=999000000000000020,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "combined-commander", TEST_GUILD_ID)

    # Create territories
    naval_territory = Territory(
        territory_id="naval-convoy-territory", name="Naval Convoy Territory",
        terrain_type="ocean", guild_id=TEST_GUILD_ID
    )
    await naval_territory.upsert(db_conn)

    aerial_territory = Territory(
        territory_id="aerial-convoy-territory", name="Aerial Convoy Territory",
        terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await aerial_territory.upsert(db_conn)

    # Create naval unit with convoy
    naval_unit = Unit(
        unit_id="combined-ship", name="Combined Ship", unit_type="ship",
        owner_character_id=character.id,
        is_naval=True,
        current_territory_id="naval-convoy-territory",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await naval_unit.upsert(db_conn)
    naval_unit = await Unit.fetch_by_unit_id(db_conn, "combined-ship", TEST_GUILD_ID)

    naval_order = Order(
        order_id="ORD-COMBINED-NAVAL",
        order_type=OrderType.UNIT.value,
        unit_ids=[naval_unit.id],
        character_id=character.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.UNIT].value,
        status=OrderStatus.ONGOING.value,
        order_data={'action': 'naval_convoy', 'path': ['naval-convoy-territory']},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await naval_order.upsert(db_conn)

    # Create aerial unit with convoy
    aerial_unit = Unit(
        unit_id="combined-bison", name="Combined Bison", unit_type="aerial",
        owner_character_id=character.id,
        is_naval=False,
        keywords=['aerial-transport'],
        current_territory_id="aerial-convoy-territory",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await aerial_unit.upsert(db_conn)
    aerial_unit = await Unit.fetch_by_unit_id(db_conn, "combined-bison", TEST_GUILD_ID)

    aerial_order = Order(
        order_id="ORD-COMBINED-AERIAL",
        order_type=OrderType.UNIT.value,
        unit_ids=[aerial_unit.id],
        character_id=character.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.UNIT].value,
        status=OrderStatus.ONGOING.value,
        order_data={'action': 'aerial_convoy', 'path': ['aerial-convoy-territory']},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await aerial_order.upsert(db_conn)

    allied_ids = {faction.id}
    enemy_ids = set()

    # Get combined convoy territories
    convoy_territories = await get_convoy_traversable_territories(
        db_conn, TEST_GUILD_ID, faction.id, allied_ids, enemy_ids
    )

    assert "naval-convoy-territory" in convoy_territories
    assert "aerial-convoy-territory" in convoy_territories


@pytest.mark.asyncio
async def test_encirclement_phase_with_convoy_support(db_conn, test_server):
    """Test full encirclement phase with convoy preventing encirclement."""
    # Create faction
    faction = Faction(faction_id="test-faction", name="Test Faction", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="test-commander", name="Test Commander",
        channel_id=999000000000000021,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "test-commander", TEST_GUILD_ID)

    # Create territories: island -> ocean (with convoy) -> mainland (friendly)
    island = Territory(
        territory_id="test-island", name="Test Island",
        terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await island.upsert(db_conn)

    ocean = Territory(
        territory_id="test-ocean", name="Test Ocean",
        terrain_type="ocean", guild_id=TEST_GUILD_ID
    )
    await ocean.upsert(db_conn)

    mainland = Territory(
        territory_id="test-mainland", name="Test Mainland",
        terrain_type="plains", controller_faction_id=faction.id,
        guild_id=TEST_GUILD_ID
    )
    await mainland.upsert(db_conn)

    adj1 = TerritoryAdjacency(territory_a_id="test-island", territory_b_id="test-ocean", guild_id=TEST_GUILD_ID)
    await adj1.upsert(db_conn)

    adj2 = TerritoryAdjacency(territory_a_id="test-mainland", territory_b_id="test-ocean", guild_id=TEST_GUILD_ID)
    await adj2.upsert(db_conn)

    # Create naval convoy
    naval_unit = Unit(
        unit_id="test-ship", name="Test Ship", unit_type="ship",
        owner_character_id=character.id,
        is_naval=True,
        current_territory_id="test-ocean",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await naval_unit.upsert(db_conn)
    naval_unit = await Unit.fetch_by_unit_id(db_conn, "test-ship", TEST_GUILD_ID)

    convoy_order = Order(
        order_id="ORD-TEST-CONVOY",
        order_type=OrderType.UNIT.value,
        unit_ids=[naval_unit.id],
        character_id=character.id,
        turn_number=1,
        phase=ORDER_PHASE_MAP[OrderType.UNIT].value,
        status=OrderStatus.ONGOING.value,
        order_data={'action': 'naval_convoy', 'path': ['test-ocean']},
        submitted_at=datetime.now(),
        guild_id=TEST_GUILD_ID
    )
    await convoy_order.upsert(db_conn)

    # Create land unit on island
    land_unit = Unit(
        unit_id="test-infantry", name="Test Infantry", unit_type="infantry",
        owner_character_id=character.id,
        is_naval=False,
        current_territory_id="test-island",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await land_unit.upsert(db_conn)

    # Run encirclement phase
    events, encircled_ids = await execute_encirclement_phase(db_conn, TEST_GUILD_ID, 1)

    # Land unit should NOT be encircled due to naval convoy
    assert len(encircled_ids) == 0
    assert len(events) == 0
