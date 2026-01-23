"""
Tests for Spirit Nexus feature including BFS pathfinding and industrial damage.
"""
import pytest
from db import (
    SpiritNexus, Territory, TerritoryAdjacency, BuildingType, Character,
    Faction, FactionMember, PlayerResources, WargameConfig
)
from handlers.spirit_nexus_handlers import (
    find_nearest_nexus, get_pole_swap_target, building_type_is_industrial,
    apply_industrial_damage, POLE_SWAP_PAIRS
)

TEST_GUILD_ID = 999999999999999999


class TestSpiritNexusModel:
    """Tests for the SpiritNexus database model."""

    @pytest.mark.asyncio
    async def test_create_nexus(self, db_conn, test_server):
        """Test creating a spirit nexus."""
        nexus = SpiritNexus(
            identifier="north-pole",
            health=100,
            territory_id="T001",
            guild_id=TEST_GUILD_ID
        )
        await nexus.upsert(db_conn)

        assert nexus.id is not None

        # Fetch and verify
        fetched = await SpiritNexus.fetch_by_identifier(db_conn, "north-pole", TEST_GUILD_ID)
        assert fetched is not None
        assert fetched.identifier == "north-pole"
        assert fetched.health == 100
        assert fetched.territory_id == "T001"

    @pytest.mark.asyncio
    async def test_update_nexus(self, db_conn, test_server):
        """Test updating a spirit nexus."""
        nexus = SpiritNexus(
            identifier="test-nexus",
            health=50,
            territory_id="T001",
            guild_id=TEST_GUILD_ID
        )
        await nexus.upsert(db_conn)

        # Update health
        nexus.health = 25
        await nexus.upsert(db_conn)

        fetched = await SpiritNexus.fetch_by_identifier(db_conn, "test-nexus", TEST_GUILD_ID)
        assert fetched.health == 25

    @pytest.mark.asyncio
    async def test_negative_health(self, db_conn, test_server):
        """Test that health can go negative."""
        nexus = SpiritNexus(
            identifier="damaged-nexus",
            health=-10,
            territory_id="T001",
            guild_id=TEST_GUILD_ID
        )
        await nexus.upsert(db_conn)

        fetched = await SpiritNexus.fetch_by_identifier(db_conn, "damaged-nexus", TEST_GUILD_ID)
        assert fetched.health == -10

    @pytest.mark.asyncio
    async def test_fetch_by_territory(self, db_conn, test_server):
        """Test fetching nexus by territory."""
        nexus = SpiritNexus(
            identifier="territory-nexus",
            health=75,
            territory_id="SPECIAL-T",
            guild_id=TEST_GUILD_ID
        )
        await nexus.upsert(db_conn)

        fetched = await SpiritNexus.fetch_by_territory(db_conn, "SPECIAL-T", TEST_GUILD_ID)
        assert fetched is not None
        assert fetched.identifier == "territory-nexus"

    @pytest.mark.asyncio
    async def test_fetch_all(self, db_conn, test_server):
        """Test fetching all nexuses."""
        nexus1 = SpiritNexus(identifier="alpha", health=10, territory_id="T1", guild_id=TEST_GUILD_ID)
        nexus2 = SpiritNexus(identifier="beta", health=20, territory_id="T2", guild_id=TEST_GUILD_ID)
        await nexus1.upsert(db_conn)
        await nexus2.upsert(db_conn)

        all_nexuses = await SpiritNexus.fetch_all(db_conn, TEST_GUILD_ID)
        assert len(all_nexuses) == 2
        # Should be sorted alphabetically
        assert all_nexuses[0].identifier == "alpha"
        assert all_nexuses[1].identifier == "beta"

    @pytest.mark.asyncio
    async def test_delete_nexus(self, db_conn, test_server):
        """Test deleting a nexus."""
        nexus = SpiritNexus(
            identifier="to-delete",
            health=5,
            territory_id="T001",
            guild_id=TEST_GUILD_ID
        )
        await nexus.upsert(db_conn)

        deleted = await SpiritNexus.delete(db_conn, "to-delete", TEST_GUILD_ID)
        assert deleted is True

        fetched = await SpiritNexus.fetch_by_identifier(db_conn, "to-delete", TEST_GUILD_ID)
        assert fetched is None

    @pytest.mark.asyncio
    async def test_verify_valid(self, db_conn, test_server):
        """Test verify() with valid data."""
        nexus = SpiritNexus(
            identifier="valid-nexus",
            health=100,
            territory_id="T001",
            guild_id=TEST_GUILD_ID
        )
        ok, error = nexus.verify()
        assert ok is True
        assert error == ""

    @pytest.mark.asyncio
    async def test_verify_empty_identifier(self, db_conn, test_server):
        """Test verify() with empty identifier."""
        nexus = SpiritNexus(
            identifier="",
            health=100,
            territory_id="T001",
            guild_id=TEST_GUILD_ID
        )
        ok, error = nexus.verify()
        assert ok is False
        assert "Identifier" in error

    @pytest.mark.asyncio
    async def test_verify_empty_territory(self, db_conn, test_server):
        """Test verify() with empty territory."""
        nexus = SpiritNexus(
            identifier="test",
            health=100,
            territory_id="",
            guild_id=TEST_GUILD_ID
        )
        ok, error = nexus.verify()
        assert ok is False
        assert "Territory" in error


class TestFindNearestNexus:
    """Tests for BFS pathfinding to find nearest nexus."""

    @pytest.mark.asyncio
    async def test_nexus_at_start_territory(self, db_conn, test_server):
        """Test finding nexus when it's at the starting territory."""
        # Create territory
        territory = Territory(
            territory_id="START",
            name="Start",
            terrain_type="land",
            guild_id=TEST_GUILD_ID
        )
        await territory.upsert(db_conn)

        # Create nexus at start
        nexus = SpiritNexus(
            identifier="local-nexus",
            health=50,
            territory_id="START",
            guild_id=TEST_GUILD_ID
        )
        await nexus.upsert(db_conn)

        found, distance = await find_nearest_nexus(db_conn, "START", TEST_GUILD_ID)
        assert found is not None
        assert found.identifier == "local-nexus"
        assert distance == 0

    @pytest.mark.asyncio
    async def test_nexus_one_hop_away(self, db_conn, test_server):
        """Test finding nexus one territory away."""
        # Create territories
        t1 = Territory(territory_id="T1", name="T1", terrain_type="land", guild_id=TEST_GUILD_ID)
        t2 = Territory(territory_id="T2", name="T2", terrain_type="land", guild_id=TEST_GUILD_ID)
        await t1.upsert(db_conn)
        await t2.upsert(db_conn)

        # Create adjacency
        adj = TerritoryAdjacency(territory_a_id="T1", territory_b_id="T2", guild_id=TEST_GUILD_ID)
        await adj.upsert(db_conn)

        # Create nexus at T2
        nexus = SpiritNexus(identifier="nearby", health=50, territory_id="T2", guild_id=TEST_GUILD_ID)
        await nexus.upsert(db_conn)

        found, distance = await find_nearest_nexus(db_conn, "T1", TEST_GUILD_ID)
        assert found is not None
        assert found.identifier == "nearby"
        assert distance == 1

    @pytest.mark.asyncio
    async def test_nexus_multiple_hops(self, db_conn, test_server):
        """Test finding nexus multiple territories away."""
        # Create chain: T1 - T2 - T3 - T4 (nexus)
        for i in range(1, 5):
            t = Territory(territory_id=f"T{i}", name=f"T{i}", terrain_type="land", guild_id=TEST_GUILD_ID)
            await t.upsert(db_conn)

        for i in range(1, 4):
            adj = TerritoryAdjacency(
                territory_a_id=f"T{i}",
                territory_b_id=f"T{i+1}",
                guild_id=TEST_GUILD_ID
            )
            await adj.upsert(db_conn)

        nexus = SpiritNexus(identifier="far-nexus", health=50, territory_id="T4", guild_id=TEST_GUILD_ID)
        await nexus.upsert(db_conn)

        found, distance = await find_nearest_nexus(db_conn, "T1", TEST_GUILD_ID)
        assert found is not None
        assert found.identifier == "far-nexus"
        assert distance == 3

    @pytest.mark.asyncio
    async def test_multiple_nexuses_pick_nearest(self, db_conn, test_server):
        """Test that BFS picks the nearest nexus."""
        # Create territories: T1 - T2 - T3
        #                          |
        #                         T4 (nexus close)
        # Also T3 has a nexus (farther)
        for tid in ["T1", "T2", "T3", "T4"]:
            t = Territory(territory_id=tid, name=tid, terrain_type="land", guild_id=TEST_GUILD_ID)
            await t.upsert(db_conn)

        # T1-T2, T2-T3, T2-T4
        for a, b in [("T1", "T2"), ("T2", "T3"), ("T2", "T4")]:
            adj = TerritoryAdjacency(territory_a_id=a, territory_b_id=b, guild_id=TEST_GUILD_ID)
            await adj.upsert(db_conn)

        # Nexus at T4 (distance 2) and T3 (distance 2 from T1)
        nexus_close = SpiritNexus(identifier="alpha-nexus", health=50, territory_id="T4", guild_id=TEST_GUILD_ID)
        nexus_far = SpiritNexus(identifier="zeta-nexus", health=50, territory_id="T3", guild_id=TEST_GUILD_ID)
        await nexus_close.upsert(db_conn)
        await nexus_far.upsert(db_conn)

        found, distance = await find_nearest_nexus(db_conn, "T1", TEST_GUILD_ID)
        assert found is not None
        # Both are distance 2, should pick alphabetically first (alpha-nexus)
        assert found.identifier == "alpha-nexus"
        assert distance == 2

    @pytest.mark.asyncio
    async def test_no_nexus_found(self, db_conn, test_server):
        """Test when no nexus exists."""
        t = Territory(territory_id="LONELY", name="Lonely", terrain_type="land", guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

        found, distance = await find_nearest_nexus(db_conn, "LONELY", TEST_GUILD_ID)
        assert found is None
        assert distance == -1

    @pytest.mark.asyncio
    async def test_traverses_ocean(self, db_conn, test_server):
        """Test that BFS traverses ocean terrain."""
        # T1 (land) - OCEAN - T2 (land with nexus)
        t1 = Territory(territory_id="T1", name="T1", terrain_type="land", guild_id=TEST_GUILD_ID)
        ocean = Territory(territory_id="OCEAN", name="Ocean", terrain_type="ocean", guild_id=TEST_GUILD_ID)
        t2 = Territory(territory_id="T2", name="T2", terrain_type="land", guild_id=TEST_GUILD_ID)
        await t1.upsert(db_conn)
        await ocean.upsert(db_conn)
        await t2.upsert(db_conn)

        adj1 = TerritoryAdjacency(territory_a_id="OCEAN", territory_b_id="T1", guild_id=TEST_GUILD_ID)
        adj2 = TerritoryAdjacency(territory_a_id="OCEAN", territory_b_id="T2", guild_id=TEST_GUILD_ID)
        await adj1.upsert(db_conn)
        await adj2.upsert(db_conn)

        nexus = SpiritNexus(identifier="ocean-nexus", health=50, territory_id="T2", guild_id=TEST_GUILD_ID)
        await nexus.upsert(db_conn)

        found, distance = await find_nearest_nexus(db_conn, "T1", TEST_GUILD_ID)
        assert found is not None
        assert found.identifier == "ocean-nexus"
        assert distance == 2  # T1 -> OCEAN -> T2


class TestPoleSwap:
    """Tests for pole swap logic."""

    def test_south_pole_swaps_to_north(self):
        """Test south-pole swaps to north-pole."""
        assert get_pole_swap_target("south-pole") == "north-pole"

    def test_north_pole_swaps_to_south(self):
        """Test north-pole swaps to south-pole."""
        assert get_pole_swap_target("north-pole") == "south-pole"

    def test_other_identifier_no_swap(self):
        """Test other identifiers don't swap."""
        assert get_pole_swap_target("random-nexus") is None
        assert get_pole_swap_target("spirit-oasis") is None


class TestBuildingTypeIsIndustrial:
    """Tests for checking if building type is industrial."""

    def test_industrial_keyword(self):
        """Test building with industrial keyword."""
        bt = BuildingType(
            type_id="factory",
            name="Factory",
            keywords=["industrial", "production"],
            guild_id=TEST_GUILD_ID
        )
        assert building_type_is_industrial(bt) is True

    def test_industrial_case_insensitive(self):
        """Test industrial keyword is case insensitive."""
        bt = BuildingType(
            type_id="factory",
            name="Factory",
            keywords=["INDUSTRIAL"],
            guild_id=TEST_GUILD_ID
        )
        assert building_type_is_industrial(bt) is True

    def test_no_industrial_keyword(self):
        """Test building without industrial keyword."""
        bt = BuildingType(
            type_id="barracks",
            name="Barracks",
            keywords=["military"],
            guild_id=TEST_GUILD_ID
        )
        assert building_type_is_industrial(bt) is False

    def test_no_keywords(self):
        """Test building with no keywords."""
        bt = BuildingType(
            type_id="house",
            name="House",
            keywords=None,
            guild_id=TEST_GUILD_ID
        )
        assert building_type_is_industrial(bt) is False

    def test_empty_keywords(self):
        """Test building with empty keywords list."""
        bt = BuildingType(
            type_id="house",
            name="House",
            keywords=[],
            guild_id=TEST_GUILD_ID
        )
        assert building_type_is_industrial(bt) is False


class TestApplyIndustrialDamage:
    """Tests for applying industrial damage to nexuses."""

    @pytest.mark.asyncio
    async def test_damage_nearest_nexus(self, db_conn, test_server):
        """Test that industrial damage is applied to nearest nexus."""
        # Setup territories
        t1 = Territory(territory_id="FACTORY", name="Factory", terrain_type="land", guild_id=TEST_GUILD_ID)
        t2 = Territory(territory_id="NEXUS", name="Nexus", terrain_type="land", guild_id=TEST_GUILD_ID)
        await t1.upsert(db_conn)
        await t2.upsert(db_conn)

        adj = TerritoryAdjacency(territory_a_id="FACTORY", territory_b_id="NEXUS", guild_id=TEST_GUILD_ID)
        await adj.upsert(db_conn)

        nexus = SpiritNexus(identifier="test-nexus", health=10, territory_id="NEXUS", guild_id=TEST_GUILD_ID)
        await nexus.upsert(db_conn)

        log = await apply_industrial_damage(
            conn=db_conn,
            territory_id="FACTORY",
            guild_id=TEST_GUILD_ID,
            turn_number=1,
            building_type_name="Steel Mill",
            building_id="BLD-0001"
        )

        assert log is not None
        assert log.event_type == "NEXUS_DAMAGED"
        assert log.event_data['nexus_identifier'] == "test-nexus"
        assert log.event_data['old_health'] == 10
        assert log.event_data['new_health'] == 9
        assert log.event_data['damage'] == 1
        assert log.event_data['was_pole_swapped'] is False

        # Verify database was updated
        updated_nexus = await SpiritNexus.fetch_by_identifier(db_conn, "test-nexus", TEST_GUILD_ID)
        assert updated_nexus.health == 9

    @pytest.mark.asyncio
    async def test_pole_swap_damage(self, db_conn, test_server):
        """Test pole swap redirects damage to opposite pole."""
        # Setup territories
        t1 = Territory(territory_id="FACTORY", name="Factory", terrain_type="land", guild_id=TEST_GUILD_ID)
        t2 = Territory(territory_id="SOUTH", name="South", terrain_type="land", guild_id=TEST_GUILD_ID)
        t3 = Territory(territory_id="NORTH", name="North", terrain_type="land", guild_id=TEST_GUILD_ID)
        await t1.upsert(db_conn)
        await t2.upsert(db_conn)
        await t3.upsert(db_conn)

        # Factory adjacent to south pole, north pole is far away
        adj = TerritoryAdjacency(territory_a_id="FACTORY", territory_b_id="SOUTH", guild_id=TEST_GUILD_ID)
        await adj.upsert(db_conn)

        south_nexus = SpiritNexus(identifier="south-pole", health=100, territory_id="SOUTH", guild_id=TEST_GUILD_ID)
        north_nexus = SpiritNexus(identifier="north-pole", health=50, territory_id="NORTH", guild_id=TEST_GUILD_ID)
        await south_nexus.upsert(db_conn)
        await north_nexus.upsert(db_conn)

        log = await apply_industrial_damage(
            conn=db_conn,
            territory_id="FACTORY",
            guild_id=TEST_GUILD_ID,
            turn_number=1,
            building_type_name="Coal Mine",
            building_id="BLD-0002"
        )

        assert log is not None
        # Should damage north-pole instead of south-pole due to swap
        assert log.event_data['nexus_identifier'] == "north-pole"
        assert log.event_data['was_pole_swapped'] is True
        assert log.event_data['original_nearest_nexus'] == "south-pole"
        assert log.event_data['old_health'] == 50
        assert log.event_data['new_health'] == 49

        # Verify south pole wasn't damaged
        south = await SpiritNexus.fetch_by_identifier(db_conn, "south-pole", TEST_GUILD_ID)
        assert south.health == 100

        # Verify north pole was damaged
        north = await SpiritNexus.fetch_by_identifier(db_conn, "north-pole", TEST_GUILD_ID)
        assert north.health == 49

    @pytest.mark.asyncio
    async def test_no_nexus_no_damage(self, db_conn, test_server):
        """Test no damage when no nexus exists."""
        t = Territory(territory_id="LONELY", name="Lonely", terrain_type="land", guild_id=TEST_GUILD_ID)
        await t.upsert(db_conn)

        log = await apply_industrial_damage(
            conn=db_conn,
            territory_id="LONELY",
            guild_id=TEST_GUILD_ID,
            turn_number=1,
            building_type_name="Factory",
            building_id="BLD-0003"
        )

        assert log is None

    @pytest.mark.asyncio
    async def test_damage_can_go_negative(self, db_conn, test_server):
        """Test that nexus health can go negative."""
        t1 = Territory(territory_id="FACTORY", name="Factory", terrain_type="land", guild_id=TEST_GUILD_ID)
        t2 = Territory(territory_id="NEXUS", name="Nexus", terrain_type="land", guild_id=TEST_GUILD_ID)
        await t1.upsert(db_conn)
        await t2.upsert(db_conn)

        adj = TerritoryAdjacency(territory_a_id="FACTORY", territory_b_id="NEXUS", guild_id=TEST_GUILD_ID)
        await adj.upsert(db_conn)

        nexus = SpiritNexus(identifier="weak-nexus", health=0, territory_id="NEXUS", guild_id=TEST_GUILD_ID)
        await nexus.upsert(db_conn)

        log = await apply_industrial_damage(
            conn=db_conn,
            territory_id="FACTORY",
            guild_id=TEST_GUILD_ID,
            turn_number=1,
            building_type_name="Factory",
            building_id="BLD-0004"
        )

        assert log is not None
        assert log.event_data['new_health'] == -1

        updated = await SpiritNexus.fetch_by_identifier(db_conn, "weak-nexus", TEST_GUILD_ID)
        assert updated.health == -1
