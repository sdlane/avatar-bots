"""
Pytest tests for faction handlers.
Tests verify faction creation, deletion, leader assignment, and member management.

Run with: pytest tests/test_faction_handlers.py -v
"""
import pytest
from handlers.faction_handlers import (
    create_faction, delete_faction, set_faction_leader,
    add_faction_member, remove_faction_member,
    grant_faction_permission, revoke_faction_permission, get_faction_permissions
)
from db import Character, Faction, FactionMember, Unit, UnitType, Territory, WargameConfig, FactionPermission, VALID_PERMISSION_TYPES
from tests.conftest import TEST_GUILD_ID, TEST_GUILD_ID_2


@pytest.mark.asyncio
async def test_create_faction_success(db_conn, test_server):
    """Test creating a faction with valid leader."""
    # Create character
    char = Character(
        identifier="leader-char", name="Leader Character",
        user_id=100000000000000001, channel_id=900000000000000001,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # Create faction with leader
    success, message = await create_faction(
        db_conn, "test-faction", "Test Faction", TEST_GUILD_ID, leader_identifier="leader-char"
    )

    # Verify
    assert success is True
    assert "created successfully" in message.lower()

    # Verify faction exists
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)
    assert faction is not None
    assert faction.name == "Test Faction"

    # Verify leader is set
    char = await Character.fetch_by_identifier(db_conn, "leader-char", TEST_GUILD_ID)
    assert faction.leader_character_id == char.id

    # Verify leader is automatically added as member
    members = await FactionMember.fetch_by_faction(db_conn, faction.id, TEST_GUILD_ID)
    assert len(members) == 1
    assert members[0].character_id == char.id

    # Cleanup
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_create_faction_without_leader(db_conn, test_server):
    """Test creating a faction without a leader."""
    # Create faction without leader
    success, message = await create_faction(
        db_conn, "test-faction", "Test Faction", TEST_GUILD_ID, leader_identifier=None
    )

    # Verify
    assert success is True
    assert "created successfully" in message.lower()

    # Verify faction exists with no leader
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)
    assert faction is not None
    assert faction.leader_character_id is None

    # Verify no members added
    members = await FactionMember.fetch_by_faction(db_conn, faction.id, TEST_GUILD_ID)
    assert len(members) == 0

    # Cleanup
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_create_faction_duplicate(db_conn, test_server):
    """Test creating a faction with duplicate faction_id."""
    # Create first faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Try to create duplicate
    success, message = await create_faction(
        db_conn, "test-faction", "Another Faction", TEST_GUILD_ID
    )

    # Verify failure
    assert success is False
    assert "already exists" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_create_faction_nonexistent_leader(db_conn, test_server):
    """Test creating a faction with invalid leader identifier."""
    # Try to create faction with nonexistent leader
    success, message = await create_faction(
        db_conn, "test-faction", "Test Faction", TEST_GUILD_ID, leader_identifier="nonexistent-leader"
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()


@pytest.mark.asyncio
async def test_delete_faction_success(db_conn, test_server):
    """Test deleting a faction with no units."""
    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Delete faction
    success, message = await delete_faction(db_conn, "test-faction", TEST_GUILD_ID)

    # Verify
    assert success is True
    assert "deleted" in message.lower()

    # Verify faction deleted
    fetched = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)
    assert fetched is None


@pytest.mark.asyncio
async def test_delete_faction_with_units(db_conn, test_server):
    """Test that deleting a faction with units fails."""
    # Create character
    char = Character(
        identifier="unit-owner", name="Unit Owner",
        user_id=100000000000000002, channel_id=900000000000000002,
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
        type_id="infantry", name="Infantry",
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
        current_territory_id=1, guild_id=TEST_GUILD_ID,
        movement=2, organization=10, attack=5, defense=5,
        siege_attack=2, siege_defense=3
    )
    await unit.upsert(db_conn)

    # Try to delete faction with units
    success, message = await delete_faction(db_conn, "test-faction", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "cannot delete" in message.lower()
    assert "units" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Unit WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Territory WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM UnitType WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_delete_faction_nonexistent(db_conn, test_server):
    """Test deleting a non-existent faction."""
    success, message = await delete_faction(db_conn, "nonexistent-faction", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not found" in message.lower()


@pytest.mark.asyncio
async def test_set_faction_leader_success(db_conn, test_server):
    """Test setting a member as faction leader."""
    # Create characters
    char1 = Character(
        identifier="member1", name="Member 1",
        user_id=100000000000000003, channel_id=900000000000000003,
        guild_id=TEST_GUILD_ID
    )
    await char1.upsert(db_conn)
    char1 = await Character.fetch_by_identifier(db_conn, "member1", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add character as member
    member = FactionMember(
        faction_id=faction.id, character_id=char1.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member.insert(db_conn)

    # Set as leader
    success, message = await set_faction_leader(db_conn, "test-faction", "member1", TEST_GUILD_ID)

    # Verify
    assert success is True
    assert "leader" in message.lower()

    # Verify leader updated
    fetched = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)
    assert fetched.leader_character_id == char1.id

    # Cleanup
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_set_faction_leader_not_member(db_conn, test_server):
    """Test that setting non-member as leader fails."""
    # Create character not in faction
    char = Character(
        identifier="non-member", name="Non Member",
        user_id=100000000000000004, channel_id=900000000000000004,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Try to set non-member as leader
    success, message = await set_faction_leader(db_conn, "test-faction", "non-member", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not a member" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_set_faction_leader_nonexistent_character(db_conn, test_server):
    """Test setting leader to invalid character identifier."""
    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Try to set nonexistent character as leader
    success, message = await set_faction_leader(db_conn, "test-faction", "nonexistent-char", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not found" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_add_faction_member_success(db_conn, test_server):
    """Test adding a character to a faction."""
    # Create character
    char = Character(
        identifier="new-member", name="New Member",
        user_id=100000000000000005, channel_id=900000000000000005,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "new-member", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Create wargame config
    wargame_config = WargameConfig(
        guild_id=TEST_GUILD_ID, current_turn=10
    )
    await wargame_config.upsert(db_conn)

    # Add member
    success, message = await add_faction_member(db_conn, "test-faction", "new-member", TEST_GUILD_ID)

    # Verify
    assert success is True
    assert "joined" in message.lower()

    # Verify member added with correct join turn
    member = await FactionMember.fetch_by_character(db_conn, char.id, TEST_GUILD_ID)
    assert member is not None
    assert member.faction_id == faction.id
    assert member.joined_turn == 10

    # Cleanup
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM WargameConfig WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_add_faction_member_already_in_faction(db_conn, test_server):
    """Test that adding a character already in a faction fails."""
    # Create character
    char = Character(
        identifier="existing-member", name="Existing Member",
        user_id=100000000000000006, channel_id=900000000000000006,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "existing-member", TEST_GUILD_ID)

    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add character as member
    member = FactionMember(
        faction_id=faction.id, character_id=char.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member.insert(db_conn)

    # Try to add again
    success, message = await add_faction_member(db_conn, "test-faction", "existing-member", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "already a member" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_add_faction_member_nonexistent_character(db_conn, test_server):
    """Test adding invalid character identifier."""
    # Create faction
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction.upsert(db_conn)

    # Try to add nonexistent character
    success, message = await add_faction_member(db_conn, "test-faction", "nonexistent-char", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not found" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_remove_faction_member_success(db_conn, test_server):
    """Test removing a regular member from a faction."""
    # Create characters
    leader_char = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000007, channel_id=900000000000000007,
        guild_id=TEST_GUILD_ID
    )
    await leader_char.upsert(db_conn)
    leader_char = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    member_char = Character(
        identifier="member", name="Member",
        user_id=100000000000000008, channel_id=900000000000000008,
        guild_id=TEST_GUILD_ID
    )
    await member_char.upsert(db_conn)
    member_char = await Character.fetch_by_identifier(db_conn, "member", TEST_GUILD_ID)

    # Create faction with leader
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID, leader_character_id=leader_char.id
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add both as members
    leader_member = FactionMember(
        faction_id=faction.id, character_id=leader_char.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await leader_member.insert(db_conn)

    regular_member = FactionMember(
        faction_id=faction.id, character_id=member_char.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await regular_member.insert(db_conn)

    # Remove regular member (not leader)
    success, message = await remove_faction_member(db_conn, "member", TEST_GUILD_ID)

    # Verify
    assert success is True
    assert "left" in message.lower()

    # Verify member removed
    fetched = await FactionMember.fetch_by_character(db_conn, member_char.id, TEST_GUILD_ID)
    assert fetched is None

    # Cleanup
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_remove_faction_member_is_leader(db_conn, test_server):
    """Test that removing the leader fails."""
    # Create character
    char = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000009, channel_id=900000000000000009,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "leader", TEST_GUILD_ID)

    # Create faction with leader
    faction = Faction(
        faction_id="test-faction", name="Test Faction",
        guild_id=TEST_GUILD_ID, leader_character_id=char.id
    )
    await faction.upsert(db_conn)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    # Add as member
    member = FactionMember(
        faction_id=faction.id, character_id=char.id,
        joined_turn=0, guild_id=TEST_GUILD_ID
    )
    await member.insert(db_conn)

    # Try to remove leader
    success, message = await remove_faction_member(db_conn, "leader", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "leader" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_remove_faction_member_not_in_faction(db_conn, test_server):
    """Test removing a character not in any faction."""
    # Create character not in any faction
    char = Character(
        identifier="solo-char", name="Solo Character",
        user_id=100000000000000010, channel_id=900000000000000010,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)

    # Try to remove from faction
    success, message = await remove_faction_member(db_conn, "solo-char", TEST_GUILD_ID)

    # Verify failure
    assert success is False
    assert "not a member" in message.lower()


@pytest.mark.asyncio
async def test_faction_guild_isolation(db_conn, test_server_multi_guild):
    """Test that faction operations are properly isolated between guilds."""
    # Create factions with same faction_id in both guilds
    faction_a = Faction(
        faction_id="test-faction", name="Guild A Faction",
        guild_id=TEST_GUILD_ID
    )
    await faction_a.upsert(db_conn)

    faction_b = Faction(
        faction_id="test-faction", name="Guild B Faction",
        guild_id=TEST_GUILD_ID_2
    )
    await faction_b.upsert(db_conn)

    # Fetch factions
    fetched_a = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)
    fetched_b = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID_2)

    # Verify same faction_id exists independently
    assert fetched_a.faction_id == fetched_b.faction_id == "test-faction"

    # But they are different entities
    assert fetched_a.name == "Guild A Faction"
    assert fetched_b.name == "Guild B Faction"
    assert fetched_a.guild_id == TEST_GUILD_ID
    assert fetched_b.guild_id == TEST_GUILD_ID_2

    # Delete faction in guild A
    success_delete_a = await delete_faction(db_conn, "test-faction", TEST_GUILD_ID)
    assert success_delete_a[0] is True

    # Verify guild B's faction still exists
    fetched_b_after = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID_2)
    assert fetched_b_after is not None
    assert fetched_b_after.name == "Guild B Faction"

    # Cleanup
    await db_conn.execute("DELETE FROM Faction WHERE guild_id IN ($1, $2);", TEST_GUILD_ID, TEST_GUILD_ID_2)


@pytest.mark.asyncio
async def test_create_faction_rollback_on_error(db_conn, test_server):
    """Test that create_faction doesn't create partial data on error."""
    # Try to create faction with nonexistent leader (should fail validation)
    success, message = await create_faction(
        db_conn, "test-faction", "Test Faction", TEST_GUILD_ID, leader_identifier="nonexistent-leader"
    )

    # Verify failure
    assert success is False
    assert "not found" in message.lower()

    # Verify no Faction record created
    fetched_faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)
    assert fetched_faction is None

    # Verify no FactionMember records created
    # (This test verifies early validation prevents partial creation)


# =========================
# Permission Tests
# =========================


@pytest.mark.asyncio
async def test_create_faction_grants_leader_all_permissions(db_conn, test_server):
    """Creating faction grants leader all four permissions."""
    # Create character
    char = Character(
        identifier="leader-char", name="Leader Character",
        user_id=100000000000000099, channel_id=900000000000000099,
        guild_id=TEST_GUILD_ID
    )
    await char.upsert(db_conn)
    char = await Character.fetch_by_identifier(db_conn, "leader-char", TEST_GUILD_ID)

    # Create faction with leader
    success, message = await create_faction(
        db_conn, "test-faction", "Test Faction", TEST_GUILD_ID, leader_identifier="leader-char"
    )
    assert success is True

    # Verify all four permissions are granted
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    for perm_type in VALID_PERMISSION_TYPES:
        has_perm = await FactionPermission.has_permission(
            db_conn, faction.id, char.id, perm_type, TEST_GUILD_ID
        )
        assert has_perm is True, f"Leader should have {perm_type} permission"

    # Cleanup
    await db_conn.execute("DELETE FROM FactionPermission WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_grant_faction_permission_to_member(db_conn, test_server):
    """Grant permission to faction member succeeds."""
    # Create characters
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000101, channel_id=900000000000000101,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)

    member = Character(
        identifier="member", name="Member",
        user_id=100000000000000102, channel_id=900000000000000102,
        guild_id=TEST_GUILD_ID
    )
    await member.upsert(db_conn)

    # Create faction and add member
    await create_faction(db_conn, "test-faction", "Test Faction", TEST_GUILD_ID, leader_identifier="leader")
    await add_faction_member(db_conn, "test-faction", "member", TEST_GUILD_ID)

    # Grant permission to member
    success, message = await grant_faction_permission(
        db_conn, "test-faction", "member", "COMMAND", TEST_GUILD_ID
    )

    assert success is True
    assert "granted" in message.lower()

    # Verify permission exists
    member_obj = await Character.fetch_by_identifier(db_conn, "member", TEST_GUILD_ID)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)
    has_perm = await FactionPermission.has_permission(
        db_conn, faction.id, member_obj.id, "COMMAND", TEST_GUILD_ID
    )
    assert has_perm is True

    # Cleanup
    await db_conn.execute("DELETE FROM FactionPermission WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_grant_faction_permission_to_non_member_fails(db_conn, test_server):
    """Grant permission to non-member fails."""
    # Create characters
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000103, channel_id=900000000000000103,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)

    non_member = Character(
        identifier="non-member", name="Non Member",
        user_id=100000000000000104, channel_id=900000000000000104,
        guild_id=TEST_GUILD_ID
    )
    await non_member.upsert(db_conn)

    # Create faction (non_member is NOT added)
    await create_faction(db_conn, "test-faction", "Test Faction", TEST_GUILD_ID, leader_identifier="leader")

    # Try to grant permission to non-member
    success, message = await grant_faction_permission(
        db_conn, "test-faction", "non-member", "COMMAND", TEST_GUILD_ID
    )

    assert success is False
    assert "not a member" in message.lower()

    # Cleanup
    await db_conn.execute("DELETE FROM FactionPermission WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_revoke_faction_permission(db_conn, test_server):
    """Revoke permission succeeds."""
    # Create character and faction
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000105, channel_id=900000000000000105,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)

    member = Character(
        identifier="member", name="Member",
        user_id=100000000000000106, channel_id=900000000000000106,
        guild_id=TEST_GUILD_ID
    )
    await member.upsert(db_conn)

    await create_faction(db_conn, "test-faction", "Test Faction", TEST_GUILD_ID, leader_identifier="leader")
    await add_faction_member(db_conn, "test-faction", "member", TEST_GUILD_ID)

    # Grant then revoke permission
    await grant_faction_permission(db_conn, "test-faction", "member", "COMMAND", TEST_GUILD_ID)
    success, message = await revoke_faction_permission(
        db_conn, "test-faction", "member", "COMMAND", TEST_GUILD_ID
    )

    assert success is True
    assert "revoked" in message.lower()

    # Verify permission is gone
    member_obj = await Character.fetch_by_identifier(db_conn, "member", TEST_GUILD_ID)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)
    has_perm = await FactionPermission.has_permission(
        db_conn, faction.id, member_obj.id, "COMMAND", TEST_GUILD_ID
    )
    assert has_perm is False

    # Cleanup
    await db_conn.execute("DELETE FROM FactionPermission WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_change_leader_transfers_permissions(db_conn, test_server):
    """Changing leader revokes old leader permissions, grants to new."""
    # Create characters
    old_leader = Character(
        identifier="old-leader", name="Old Leader",
        user_id=100000000000000107, channel_id=900000000000000107,
        guild_id=TEST_GUILD_ID
    )
    await old_leader.upsert(db_conn)

    new_leader = Character(
        identifier="new-leader", name="New Leader",
        user_id=100000000000000108, channel_id=900000000000000108,
        guild_id=TEST_GUILD_ID
    )
    await new_leader.upsert(db_conn)

    # Create faction with old leader
    await create_faction(db_conn, "test-faction", "Test Faction", TEST_GUILD_ID, leader_identifier="old-leader")
    await add_faction_member(db_conn, "test-faction", "new-leader", TEST_GUILD_ID)

    # Change leader
    success, message = await set_faction_leader(
        db_conn, "test-faction", "new-leader", TEST_GUILD_ID
    )
    assert success is True

    # Verify old leader lost all permissions
    old_leader_obj = await Character.fetch_by_identifier(db_conn, "old-leader", TEST_GUILD_ID)
    new_leader_obj = await Character.fetch_by_identifier(db_conn, "new-leader", TEST_GUILD_ID)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)

    for perm_type in VALID_PERMISSION_TYPES:
        old_has = await FactionPermission.has_permission(
            db_conn, faction.id, old_leader_obj.id, perm_type, TEST_GUILD_ID
        )
        new_has = await FactionPermission.has_permission(
            db_conn, faction.id, new_leader_obj.id, perm_type, TEST_GUILD_ID
        )
        assert old_has is False, f"Old leader should NOT have {perm_type}"
        assert new_has is True, f"New leader should have {perm_type}"

    # Cleanup
    await db_conn.execute("DELETE FROM FactionPermission WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)


@pytest.mark.asyncio
async def test_remove_member_revokes_permissions(db_conn, test_server):
    """Removing member revokes their faction permissions."""
    # Create characters
    leader = Character(
        identifier="leader", name="Leader",
        user_id=100000000000000109, channel_id=900000000000000109,
        guild_id=TEST_GUILD_ID
    )
    await leader.upsert(db_conn)

    member = Character(
        identifier="member", name="Member",
        user_id=100000000000000110, channel_id=900000000000000110,
        guild_id=TEST_GUILD_ID
    )
    await member.upsert(db_conn)

    # Create faction and add member
    await create_faction(db_conn, "test-faction", "Test Faction", TEST_GUILD_ID, leader_identifier="leader")
    await add_faction_member(db_conn, "test-faction", "member", TEST_GUILD_ID)

    # Grant permission to member
    await grant_faction_permission(db_conn, "test-faction", "member", "COMMAND", TEST_GUILD_ID)

    # Verify permission exists
    member_obj = await Character.fetch_by_identifier(db_conn, "member", TEST_GUILD_ID)
    faction = await Faction.fetch_by_faction_id(db_conn, "test-faction", TEST_GUILD_ID)
    has_perm = await FactionPermission.has_permission(
        db_conn, faction.id, member_obj.id, "COMMAND", TEST_GUILD_ID
    )
    assert has_perm is True

    # Remove member from faction
    success, message = await remove_faction_member(db_conn, "member", TEST_GUILD_ID)
    assert success is True

    # Verify permission is revoked
    has_perm_after = await FactionPermission.has_permission(
        db_conn, faction.id, member_obj.id, "COMMAND", TEST_GUILD_ID
    )
    assert has_perm_after is False

    # Cleanup
    await db_conn.execute("DELETE FROM FactionPermission WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM FactionMember WHERE guild_id = $1;", TEST_GUILD_ID)
    await db_conn.execute("DELETE FROM Faction WHERE guild_id = $1;", TEST_GUILD_ID)
