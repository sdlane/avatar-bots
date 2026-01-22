"""
Pytest tests for the encirclement phase in turn resolution.
Tests verify encirclement detection, organization penalties, and event generation.

Run with: docker compose -f ~/avatar-bots/docker-compose-development.yaml exec iroh-api pytest tests/test_encirclement.py -v
"""
import pytest
from handlers.turn_handlers import execute_encirclement_phase, execute_upkeep_phase
from handlers.encirclement_handlers import (
    get_allied_faction_ids,
    get_enemy_faction_ids,
    get_territory_controller_faction,
    is_territory_traversable,
    is_friendly_territory,
    bfs_can_reach_friendly,
    check_unit_encircled,
    get_unit_home_faction_id,
)
from db import (
    Character, Unit, Territory, TerritoryAdjacency, Faction,
    Alliance, War, WarParticipant, PlayerResources, FactionMember
)
from tests.conftest import TEST_GUILD_ID


# =============================================================================
# Helper function tests
# =============================================================================

@pytest.mark.asyncio
async def test_get_allied_faction_ids_no_alliances(db_conn, test_server):
    """Test that a faction with no alliances only returns itself."""
    # Create faction
    faction = Faction(
        faction_id="earth-kingdom", name="Earth Kingdom",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    allies = await get_allied_faction_ids(db_conn, faction.id, TEST_GUILD_ID)

    assert allies == {faction.id}


@pytest.mark.asyncio
async def test_get_allied_faction_ids_with_alliance(db_conn, test_server):
    """Test that active alliances are included."""
    # Create two factions
    faction1 = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    faction2 = Faction(faction_id="water-tribe", name="Water Tribe", guild_id=TEST_GUILD_ID)
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "water-tribe", TEST_GUILD_ID)

    # Create active alliance
    alliance = Alliance(
        faction_a_id=min(faction1.id, faction2.id),
        faction_b_id=max(faction1.id, faction2.id),
        status="ACTIVE",
        initiated_by_faction_id=faction1.id,
        guild_id=TEST_GUILD_ID
    )
    await alliance.upsert(db_conn)

    allies = await get_allied_faction_ids(db_conn, faction1.id, TEST_GUILD_ID)

    assert faction1.id in allies
    assert faction2.id in allies


@pytest.mark.asyncio
async def test_get_enemy_faction_ids_no_wars(db_conn, test_server):
    """Test that a faction with no wars has no enemies."""
    faction = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    enemies = await get_enemy_faction_ids(db_conn, faction.id, TEST_GUILD_ID)

    assert enemies == set()


@pytest.mark.asyncio
async def test_get_enemy_faction_ids_with_war(db_conn, test_server):
    """Test that factions on opposite side of war are enemies."""
    # Create two factions
    faction1 = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    faction2 = Faction(faction_id="fire-nation", name="Fire Nation", guild_id=TEST_GUILD_ID)
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "fire-nation", TEST_GUILD_ID)

    # Create war
    war = War(war_id="WAR-01", objective="Conquest", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war.upsert(db_conn)
    war = await War.fetch_by_id(db_conn, "WAR-01", TEST_GUILD_ID)

    # Add participants on opposite sides
    wp1 = WarParticipant(
        war_id=war.id, faction_id=faction1.id, side="SIDE_A",
        joined_turn=1, is_original_declarer=True, guild_id=TEST_GUILD_ID
    )
    await wp1.upsert(db_conn)

    wp2 = WarParticipant(
        war_id=war.id, faction_id=faction2.id, side="SIDE_B",
        joined_turn=1, is_original_declarer=False, guild_id=TEST_GUILD_ID
    )
    await wp2.upsert(db_conn)

    enemies = await get_enemy_faction_ids(db_conn, faction1.id, TEST_GUILD_ID)

    assert faction2.id in enemies
    assert faction1.id not in enemies


@pytest.mark.asyncio
async def test_get_territory_controller_faction_uncontrolled(db_conn, test_server):
    """Test that uncontrolled territory returns None."""
    territory = Territory(
        territory_id="neutral-lands", name="Neutral Lands",
        terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)
    territory = await Territory.fetch_by_territory_id(db_conn, "neutral-lands", TEST_GUILD_ID)

    controller = await get_territory_controller_faction(db_conn, territory, TEST_GUILD_ID)

    assert controller is None


@pytest.mark.asyncio
async def test_get_territory_controller_faction_character_controlled(db_conn, test_server):
    """Test that character-controlled territory uses represented_faction_id."""
    # Create faction
    faction = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    # Create character representing the faction
    character = Character(
        identifier="bumi", name="King Bumi",
        channel_id=999000000000000001,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "bumi", TEST_GUILD_ID)

    # Create territory controlled by character
    territory = Territory(
        territory_id="omashu", name="Omashu",
        terrain_type="mountain", controller_character_id=character.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)
    territory = await Territory.fetch_by_territory_id(db_conn, "omashu", TEST_GUILD_ID)

    controller = await get_territory_controller_faction(db_conn, territory, TEST_GUILD_ID)

    assert controller == faction.id


@pytest.mark.asyncio
async def test_get_territory_controller_faction_faction_controlled(db_conn, test_server):
    """Test that faction-controlled territory returns faction ID directly."""
    # Create faction
    faction = Faction(faction_id="fire-nation", name="Fire Nation", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "fire-nation", TEST_GUILD_ID)

    # Create territory controlled by faction
    territory = Territory(
        territory_id="capital-city", name="Capital City",
        terrain_type="plains", controller_faction_id=faction.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)
    territory = await Territory.fetch_by_territory_id(db_conn, "capital-city", TEST_GUILD_ID)

    controller = await get_territory_controller_faction(db_conn, territory, TEST_GUILD_ID)

    assert controller == faction.id


# =============================================================================
# BFS path finding tests
# =============================================================================

@pytest.mark.asyncio
async def test_bfs_unit_in_friendly_territory(db_conn, test_server):
    """Test that unit in friendly territory is NOT encircled."""
    # Create faction
    faction = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    # Create friendly territory
    territory = Territory(
        territory_id="ba-sing-se", name="Ba Sing Se",
        terrain_type="plains", controller_faction_id=faction.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    allied_ids = {faction.id}
    enemy_ids = set()

    can_reach = await bfs_can_reach_friendly(
        db_conn, "ba-sing-se", faction.id, allied_ids, enemy_ids, TEST_GUILD_ID
    )

    assert can_reach is True


@pytest.mark.asyncio
async def test_bfs_path_through_uncontrolled_territory(db_conn, test_server):
    """Test that BFS finds path through uncontrolled territories."""
    # Create faction
    faction = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    # Create territories: start -> uncontrolled -> friendly
    start = Territory(
        territory_id="outpost", name="Outpost",
        terrain_type="plains", guild_id=TEST_GUILD_ID  # uncontrolled
    )
    await start.upsert(db_conn)

    middle = Territory(
        territory_id="wilderness", name="Wilderness",
        terrain_type="forest", guild_id=TEST_GUILD_ID  # uncontrolled
    )
    await middle.upsert(db_conn)

    friendly = Territory(
        territory_id="ba-sing-se", name="Ba Sing Se",
        terrain_type="plains", controller_faction_id=faction.id,
        guild_id=TEST_GUILD_ID
    )
    await friendly.upsert(db_conn)

    # Create adjacencies
    adj1 = TerritoryAdjacency(territory_a_id="outpost", territory_b_id="wilderness", guild_id=TEST_GUILD_ID)
    await adj1.upsert(db_conn)

    adj2 = TerritoryAdjacency(territory_a_id="ba-sing-se", territory_b_id="wilderness", guild_id=TEST_GUILD_ID)
    await adj2.upsert(db_conn)

    allied_ids = {faction.id}
    enemy_ids = set()

    can_reach = await bfs_can_reach_friendly(
        db_conn, "outpost", faction.id, allied_ids, enemy_ids, TEST_GUILD_ID
    )

    assert can_reach is True


@pytest.mark.asyncio
async def test_bfs_blocked_by_enemy_territory(db_conn, test_server):
    """Test that BFS is blocked by enemy territories."""
    # Create factions
    faction1 = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    faction2 = Faction(faction_id="fire-nation", name="Fire Nation", guild_id=TEST_GUILD_ID)
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "fire-nation", TEST_GUILD_ID)

    # Create territories: start -> enemy -> friendly (should be blocked)
    start = Territory(
        territory_id="isolated", name="Isolated",
        terrain_type="plains", guild_id=TEST_GUILD_ID  # uncontrolled
    )
    await start.upsert(db_conn)

    enemy = Territory(
        territory_id="occupied", name="Occupied",
        terrain_type="plains", controller_faction_id=faction2.id,
        guild_id=TEST_GUILD_ID
    )
    await enemy.upsert(db_conn)

    friendly = Territory(
        territory_id="ba-sing-se", name="Ba Sing Se",
        terrain_type="plains", controller_faction_id=faction1.id,
        guild_id=TEST_GUILD_ID
    )
    await friendly.upsert(db_conn)

    # Create adjacencies
    adj1 = TerritoryAdjacency(territory_a_id="isolated", territory_b_id="occupied", guild_id=TEST_GUILD_ID)
    await adj1.upsert(db_conn)

    adj2 = TerritoryAdjacency(territory_a_id="ba-sing-se", territory_b_id="occupied", guild_id=TEST_GUILD_ID)
    await adj2.upsert(db_conn)

    allied_ids = {faction1.id}
    enemy_ids = {faction2.id}

    can_reach = await bfs_can_reach_friendly(
        db_conn, "isolated", faction1.id, allied_ids, enemy_ids, TEST_GUILD_ID
    )

    assert can_reach is False


@pytest.mark.asyncio
async def test_bfs_blocked_by_ocean(db_conn, test_server):
    """Test that BFS is blocked by ocean terrain."""
    # Create faction
    faction = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    # Create territories: start -> ocean -> friendly (should be blocked)
    start = Territory(
        territory_id="island", name="Island",
        terrain_type="plains", guild_id=TEST_GUILD_ID  # uncontrolled
    )
    await start.upsert(db_conn)

    ocean = Territory(
        territory_id="ocean-tile", name="Ocean",
        terrain_type="ocean", guild_id=TEST_GUILD_ID
    )
    await ocean.upsert(db_conn)

    friendly = Territory(
        territory_id="mainland", name="Mainland",
        terrain_type="plains", controller_faction_id=faction.id,
        guild_id=TEST_GUILD_ID
    )
    await friendly.upsert(db_conn)

    # Create adjacencies
    adj1 = TerritoryAdjacency(territory_a_id="island", territory_b_id="ocean-tile", guild_id=TEST_GUILD_ID)
    await adj1.upsert(db_conn)

    adj2 = TerritoryAdjacency(territory_a_id="mainland", territory_b_id="ocean-tile", guild_id=TEST_GUILD_ID)
    await adj2.upsert(db_conn)

    allied_ids = {faction.id}
    enemy_ids = set()

    can_reach = await bfs_can_reach_friendly(
        db_conn, "island", faction.id, allied_ids, enemy_ids, TEST_GUILD_ID
    )

    assert can_reach is False


# =============================================================================
# Unit encirclement tests
# =============================================================================

@pytest.mark.asyncio
async def test_naval_unit_never_encircled(db_conn, test_server):
    """Test that naval units are never encircled."""
    # Create faction
    faction = Faction(faction_id="water-tribe", name="Water Tribe", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "water-tribe", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="katara", name="Katara",
        channel_id=999000000000000002,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "katara", TEST_GUILD_ID)

    # Create territory (isolated, no friendly connection)
    territory = Territory(
        territory_id="isolated-sea", name="Isolated Sea",
        terrain_type="ocean", guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create naval unit
    unit = Unit(
        unit_id="ship-01", name="Water Tribe Ship", unit_type="ship",
        owner_character_id=character.id,
        is_naval=True,
        current_territory_id="isolated-sea",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "ship-01", TEST_GUILD_ID)

    is_encircled = await check_unit_encircled(db_conn, unit, TEST_GUILD_ID)

    assert is_encircled is False


@pytest.mark.asyncio
async def test_unaffiliated_unit_always_encircled(db_conn, test_server):
    """Test that units with no home faction (unaffiliated) are always encircled."""
    # Create character with NO represented faction
    character = Character(
        identifier="wanderer", name="The Wanderer",
        channel_id=999000000000000003,
        represented_faction_id=None, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "wanderer", TEST_GUILD_ID)

    # Create territory
    territory = Territory(
        territory_id="wilderness", name="Wilderness",
        terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create land unit
    unit = Unit(
        unit_id="wanderer-unit", name="Wanderer's Guard", unit_type="infantry",
        owner_character_id=character.id,
        is_naval=False,
        current_territory_id="wilderness",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "wanderer-unit", TEST_GUILD_ID)

    is_encircled = await check_unit_encircled(db_conn, unit, TEST_GUILD_ID)

    assert is_encircled is True


@pytest.mark.asyncio
async def test_faction_owned_unit_uses_owner_faction_id(db_conn, test_server):
    """Test that faction-owned units use owner_faction_id as home faction."""
    # Create faction
    faction = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    # Create friendly territory
    territory = Territory(
        territory_id="ba-sing-se", name="Ba Sing Se",
        terrain_type="plains", controller_faction_id=faction.id,
        guild_id=TEST_GUILD_ID
    )
    await territory.upsert(db_conn)

    # Create faction-owned unit
    unit = Unit(
        unit_id="royal-guard", name="Royal Guard", unit_type="infantry",
        owner_faction_id=faction.id,
        is_naval=False,
        current_territory_id="ba-sing-se",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "royal-guard", TEST_GUILD_ID)

    home_faction = await get_unit_home_faction_id(db_conn, unit, TEST_GUILD_ID)

    assert home_faction == faction.id

    is_encircled = await check_unit_encircled(db_conn, unit, TEST_GUILD_ID)

    assert is_encircled is False


# =============================================================================
# Encirclement phase integration tests
# =============================================================================

@pytest.mark.asyncio
async def test_encirclement_phase_generates_event(db_conn, test_server):
    """Test that encirclement phase generates UNIT_ENCIRCLED event."""
    # Create factions
    faction1 = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction1.upsert(db_conn)
    faction1 = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    faction2 = Faction(faction_id="fire-nation", name="Fire Nation", guild_id=TEST_GUILD_ID)
    await faction2.upsert(db_conn)
    faction2 = await Faction.fetch_by_faction_id(db_conn, "fire-nation", TEST_GUILD_ID)

    # Create war between factions
    war = War(war_id="WAR-01", objective="Conquest", declared_turn=1, guild_id=TEST_GUILD_ID)
    await war.upsert(db_conn)
    war = await War.fetch_by_id(db_conn, "WAR-01", TEST_GUILD_ID)

    wp1 = WarParticipant(war_id=war.id, faction_id=faction1.id, side="SIDE_A", joined_turn=1, guild_id=TEST_GUILD_ID)
    await wp1.upsert(db_conn)
    wp2 = WarParticipant(war_id=war.id, faction_id=faction2.id, side="SIDE_B", joined_turn=1, guild_id=TEST_GUILD_ID)
    await wp2.upsert(db_conn)

    # Create character
    character = Character(
        identifier="toph", name="Toph Beifong",
        channel_id=999000000000000004,
        represented_faction_id=faction1.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "toph", TEST_GUILD_ID)

    # Create territories - unit surrounded by enemy
    isolated = Territory(
        territory_id="surrounded", name="Surrounded",
        terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await isolated.upsert(db_conn)

    enemy1 = Territory(
        territory_id="enemy-1", name="Enemy Territory 1",
        terrain_type="plains", controller_faction_id=faction2.id,
        guild_id=TEST_GUILD_ID
    )
    await enemy1.upsert(db_conn)

    # Create adjacency (only exit is through enemy)
    adj = TerritoryAdjacency(territory_a_id="enemy-1", territory_b_id="surrounded", guild_id=TEST_GUILD_ID)
    await adj.upsert(db_conn)

    # Create unit in surrounded territory
    unit = Unit(
        unit_id="encircled-unit", name="Encircled Unit", unit_type="infantry",
        owner_character_id=character.id,
        is_naval=False,
        current_territory_id="surrounded",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "encircled-unit", TEST_GUILD_ID)

    # Execute encirclement phase
    events, encircled_ids = await execute_encirclement_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify UNIT_ENCIRCLED event generated
    assert len(events) == 1
    event = events[0]
    assert event.event_type == 'UNIT_ENCIRCLED'
    assert event.event_data['unit_id'] == 'encircled-unit'
    assert event.event_data['territory_id'] == 'surrounded'
    assert event.event_data['home_faction_id'] == faction1.id
    assert character.id in event.event_data['affected_character_ids']

    # Verify unit is in encircled set
    assert unit.id in encircled_ids


@pytest.mark.asyncio
async def test_encirclement_phase_not_encircled_if_path_exists(db_conn, test_server):
    """Test that unit is NOT encircled if path to friendly territory exists."""
    # Create faction
    faction = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="sokka", name="Sokka",
        channel_id=999000000000000005,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "sokka", TEST_GUILD_ID)

    # Create connected friendly territories
    outpost = Territory(
        territory_id="outpost", name="Outpost",
        terrain_type="plains", guild_id=TEST_GUILD_ID
    )
    await outpost.upsert(db_conn)

    base = Territory(
        territory_id="base", name="Base",
        terrain_type="plains", controller_faction_id=faction.id,
        guild_id=TEST_GUILD_ID
    )
    await base.upsert(db_conn)

    # Create adjacency
    adj = TerritoryAdjacency(territory_a_id="base", territory_b_id="outpost", guild_id=TEST_GUILD_ID)
    await adj.upsert(db_conn)

    # Create unit at outpost
    unit = Unit(
        unit_id="safe-unit", name="Safe Unit", unit_type="infantry",
        owner_character_id=character.id,
        is_naval=False,
        current_territory_id="outpost",
        organization=10, max_organization=10,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)

    # Execute encirclement phase
    events, encircled_ids = await execute_encirclement_phase(db_conn, TEST_GUILD_ID, 1)

    # Verify no encirclement events
    assert len(events) == 0
    assert len(encircled_ids) == 0


# =============================================================================
# Upkeep with encirclement tests
# =============================================================================

@pytest.mark.asyncio
async def test_encircled_unit_loses_organization_but_no_resources_spent(db_conn, test_server):
    """Test that encircled units lose organization but resources are NOT spent."""
    # Create faction
    faction = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="zuko", name="Zuko",
        channel_id=999000000000000006,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "zuko", TEST_GUILD_ID)

    # Create player resources
    resources = PlayerResources(
        character_id=character.id,
        ore=100, lumber=100, coal=100, rations=100, cloth=100, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Create unit with upkeep (3 resource types)
    unit = Unit(
        unit_id="encircled-unit", name="Encircled Unit", unit_type="infantry",
        owner_character_id=character.id,
        is_naval=False,
        current_territory_id="somewhere",
        organization=10, max_organization=10,
        upkeep_ore=5, upkeep_lumber=3, upkeep_rations=10,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "encircled-unit", TEST_GUILD_ID)

    # Simulate encircled unit
    encircled_ids = {unit.id}

    # Execute upkeep phase with encircled unit
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1, encircled_ids)

    # Verify UPKEEP_ENCIRCLED event generated
    encircled_events = [e for e in events if e.event_type == 'UPKEEP_ENCIRCLED']
    assert len(encircled_events) == 1
    event = encircled_events[0]
    assert event.event_data['unit_id'] == 'encircled-unit'
    # Organization penalty = count of resource types needed (3 types: ore, lumber, rations)
    assert event.event_data['organization_penalty'] == 3
    assert event.event_data['new_organization'] == 7  # 10 - 3
    assert set(event.event_data['resource_types_needed']) == {'ore', 'lumber', 'rations'}

    # Verify unit organization reduced
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "encircled-unit", TEST_GUILD_ID)
    assert updated_unit.organization == 7

    # Verify resources were NOT spent
    updated_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert updated_resources.ore == 100  # unchanged
    assert updated_resources.lumber == 100  # unchanged
    assert updated_resources.rations == 100  # unchanged


@pytest.mark.asyncio
async def test_encircled_unit_with_zero_upkeep_no_penalty(db_conn, test_server):
    """Test that encircled unit with zero upkeep has no penalty."""
    # Create faction
    faction = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="iroh", name="Uncle Iroh",
        channel_id=999000000000000007,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "iroh", TEST_GUILD_ID)

    # Create unit with NO upkeep
    unit = Unit(
        unit_id="free-unit", name="Free Unit", unit_type="militia",
        owner_character_id=character.id,
        is_naval=False,
        current_territory_id="somewhere",
        organization=10, max_organization=10,
        upkeep_ore=0, upkeep_lumber=0, upkeep_coal=0,
        upkeep_rations=0, upkeep_cloth=0,
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "free-unit", TEST_GUILD_ID)

    # Simulate encircled unit
    encircled_ids = {unit.id}

    # Execute upkeep phase with encircled unit
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1, encircled_ids)

    # Verify no UPKEEP_ENCIRCLED event (penalty is 0)
    encircled_events = [e for e in events if e.event_type == 'UPKEEP_ENCIRCLED']
    assert len(encircled_events) == 0

    # Verify unit organization unchanged
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "free-unit", TEST_GUILD_ID)
    assert updated_unit.organization == 10


@pytest.mark.asyncio
async def test_mixed_encircled_and_normal_units(db_conn, test_server):
    """Test upkeep with both encircled and normal units."""
    # Create faction
    faction = Faction(faction_id="earth-kingdom", name="Earth Kingdom", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "earth-kingdom", TEST_GUILD_ID)

    # Create character
    character = Character(
        identifier="aang", name="Aang",
        channel_id=999000000000000008,
        represented_faction_id=faction.id, guild_id=TEST_GUILD_ID
    )
    await character.upsert(db_conn)
    character = await Character.fetch_by_identifier(db_conn, "aang", TEST_GUILD_ID)

    # Create player resources
    resources = PlayerResources(
        character_id=character.id,
        ore=100, lumber=100, coal=100, rations=100, cloth=100, platinum=0,
        guild_id=TEST_GUILD_ID
    )
    await resources.upsert(db_conn)

    # Create encircled unit
    encircled_unit = Unit(
        unit_id="encircled-unit", name="Encircled Unit", unit_type="infantry",
        owner_character_id=character.id,
        is_naval=False,
        current_territory_id="somewhere",
        organization=10, max_organization=10,
        upkeep_ore=5, upkeep_lumber=3,  # 2 resource types
        guild_id=TEST_GUILD_ID
    )
    await encircled_unit.upsert(db_conn)
    encircled_unit = await Unit.fetch_by_unit_id(db_conn, "encircled-unit", TEST_GUILD_ID)

    # Create normal unit
    normal_unit = Unit(
        unit_id="normal-unit", name="Normal Unit", unit_type="infantry",
        owner_character_id=character.id,
        is_naval=False,
        current_territory_id="somewhere-safe",
        organization=10, max_organization=10,
        upkeep_ore=3, upkeep_rations=5,  # 2 resource types
        guild_id=TEST_GUILD_ID
    )
    await normal_unit.upsert(db_conn)
    normal_unit = await Unit.fetch_by_unit_id(db_conn, "normal-unit", TEST_GUILD_ID)

    # Only encircled_unit is encircled
    encircled_ids = {encircled_unit.id}

    # Execute upkeep phase
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1, encircled_ids)

    # Verify UPKEEP_ENCIRCLED event for encircled unit
    encircled_events = [e for e in events if e.event_type == 'UPKEEP_ENCIRCLED']
    assert len(encircled_events) == 1
    assert encircled_events[0].event_data['unit_id'] == 'encircled-unit'
    assert encircled_events[0].event_data['organization_penalty'] == 2  # 2 types

    # Verify UPKEEP_SUMMARY for normal unit (resources spent)
    summary_events = [e for e in events if e.event_type == 'UPKEEP_SUMMARY']
    assert len(summary_events) == 1
    assert summary_events[0].event_data['resources_spent']['ore'] == 3  # only normal unit
    assert summary_events[0].event_data['resources_spent']['rations'] == 5

    # Verify encircled unit organization reduced
    updated_encircled = await Unit.fetch_by_unit_id(db_conn, "encircled-unit", TEST_GUILD_ID)
    assert updated_encircled.organization == 8  # 10 - 2

    # Verify normal unit organization unchanged (full payment)
    updated_normal = await Unit.fetch_by_unit_id(db_conn, "normal-unit", TEST_GUILD_ID)
    assert updated_normal.organization == 10

    # Verify resources - only normal unit's upkeep was deducted
    updated_resources = await PlayerResources.fetch_by_character(db_conn, character.id, TEST_GUILD_ID)
    assert updated_resources.ore == 97  # 100 - 3 (normal unit only)
    assert updated_resources.lumber == 100  # unchanged (encircled unit's upkeep not spent)
    assert updated_resources.rations == 95  # 100 - 5 (normal unit only)


@pytest.mark.asyncio
async def test_faction_owned_encircled_unit(db_conn, test_server):
    """Test encirclement handling for faction-owned units."""
    # Create faction
    faction = Faction(faction_id="fire-nation", name="Fire Nation", guild_id=TEST_GUILD_ID)
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "fire-nation", TEST_GUILD_ID)

    # Create faction-owned unit
    unit = Unit(
        unit_id="faction-unit", name="Fire Nation Unit", unit_type="infantry",
        owner_faction_id=faction.id,
        is_naval=False,
        current_territory_id="somewhere",
        organization=10, max_organization=10,
        upkeep_ore=5, upkeep_coal=3, upkeep_rations=7,  # 3 types
        guild_id=TEST_GUILD_ID
    )
    await unit.upsert(db_conn)
    unit = await Unit.fetch_by_unit_id(db_conn, "faction-unit", TEST_GUILD_ID)

    # Simulate encircled unit
    encircled_ids = {unit.id}

    # Execute upkeep phase with encircled unit
    events = await execute_upkeep_phase(db_conn, TEST_GUILD_ID, 1, encircled_ids)

    # Verify FACTION_UPKEEP_ENCIRCLED event generated
    encircled_events = [e for e in events if e.event_type == 'FACTION_UPKEEP_ENCIRCLED']
    assert len(encircled_events) == 1
    event = encircled_events[0]
    assert event.event_data['unit_id'] == 'faction-unit'
    assert event.event_data['organization_penalty'] == 3  # 3 types
    assert event.event_data['new_organization'] == 7
    assert event.event_data['owner_faction_id'] == faction.faction_id

    # Verify unit organization reduced
    updated_unit = await Unit.fetch_by_unit_id(db_conn, "faction-unit", TEST_GUILD_ID)
    assert updated_unit.organization == 7
