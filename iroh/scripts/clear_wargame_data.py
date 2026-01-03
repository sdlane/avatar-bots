#!/usr/bin/env python3
"""
Clear all wargame-related data for a specific guild.

This script removes all wargame data including:
- Turn logs
- Units
- Unit types
- Territory adjacencies
- Territories
- Player resources
- Orders
- Faction members
- Faction join requests
- Factions
- Wargame config

Usage:
    python clear_wargame_data.py <guild_id>

Example:
    python clear_wargame_data.py 1234567890
"""
import asyncio
import asyncpg
import sys
from pathlib import Path

# Add parent directory to path for imports
parent_dir = Path(__file__).parent
sys.path.insert(0, str(parent_dir))


async def count_table_rows(conn: asyncpg.Connection, table: str, guild_id: int) -> int:
    """Count rows in a table for a specific guild."""
    try:
        return await conn.fetchval(
            f"SELECT COUNT(*) FROM {table} WHERE guild_id = $1;",
            guild_id
        )
    except Exception:
        return 0


async def delete_table_data(conn: asyncpg.Connection, table: str, guild_id: int) -> int:
    """Delete all rows from a table for a specific guild."""
    try:
        result = await conn.execute(
            f"DELETE FROM {table} WHERE guild_id = $1;",
            guild_id
        )
        # Extract number from result string (e.g., "DELETE 42" -> 42)
        return int(result.split()[-1]) if result.startswith("DELETE") else 0
    except Exception as e:
        print(f"Warning: Error deleting from {table}: {e}", file=sys.stderr)
        return 0


async def clear_wargame_data(conn: asyncpg.Connection, guild_id: int) -> dict:
    """
    Delete all wargame data for a specific guild.

    Args:
        conn: Database connection
        guild_id: Guild ID to clear data for

    Returns:
        Dictionary with counts of deleted rows per table
    """
    # Tables to clear in order (respects foreign key constraints)
    tables = [
        "TurnLog",
        "WargameOrder",  # Note: This is the Order table renamed to avoid SQL keyword collision
        "Unit",
        "UnitType",
        "TerritoryAdjacency",
        "Territory",
        "PlayerResources",
        "FactionMember",
        "FactionJoinRequest",
        "Faction",
        "WargameConfig",
    ]

    results = {}

    for table in tables:
        count_before = await count_table_rows(conn, table, guild_id)
        if count_before > 0:
            deleted = await delete_table_data(conn, table, guild_id)
            results[table] = {"before": count_before, "deleted": deleted}
        else:
            results[table] = {"before": 0, "deleted": 0}

    return results


async def main():
    """Main function to connect to database and clear wargame data."""
    # Check arguments
    if len(sys.argv) != 2:
        print("Error: Guild ID required", file=sys.stderr)
        print(f"\nUsage: {sys.argv[0]} <guild_id>", file=sys.stderr)
        print(f"Example: {sys.argv[0]} 1234567890", file=sys.stderr)
        sys.exit(1)

    try:
        guild_id = int(sys.argv[1])
    except ValueError:
        print(f"Error: Invalid guild ID '{sys.argv[1]}'. Must be an integer.", file=sys.stderr)
        sys.exit(1)

    # Database connection parameters
    conn = await asyncpg.connect(
        host='db',
        port=5432,
        user='AVATAR',
        password='password',
        database='AVATAR'
    )

    try:
        print(f"Clearing all wargame data for guild ID: {guild_id}")
        print("=" * 70)

        # Count entries before deletion
        tables = [
            "TurnLog",
            "WargameOrder",
            "Unit",
            "UnitType",
            "TerritoryAdjacency",
            "Territory",
            "PlayerResources",
            "FactionMember",
            "FactionJoinRequest",
            "Faction",
            "WargameConfig",
        ]

        print("\nCurrent data counts:")
        print("-" * 70)

        total_rows = 0
        counts = {}
        for table in tables:
            count = await count_table_rows(conn, table, guild_id)
            counts[table] = count
            total_rows += count
            if count > 0:
                print(f"  {table:.<30} {count:>6} rows")

        if total_rows == 0:
            print("\n  No wargame data found for this guild.")
            print("=" * 70)
            return

        print("-" * 70)
        print(f"  {'TOTAL':.<30} {total_rows:>6} rows")
        print()

        # Ask for confirmation
        response = input(f"Are you sure you want to delete ALL wargame data ({total_rows} total rows)? (yes/no): ")

        if response.lower() not in ['yes', 'y']:
            print("\nCancelled.")
            return

        # Perform deletion
        print("\nDeleting data...")
        print("-" * 70)

        results = await clear_wargame_data(conn, guild_id)

        total_deleted = 0
        for table, result in results.items():
            if result["deleted"] > 0:
                print(f"  {table:.<30} {result['deleted']:>6} rows deleted")
                total_deleted += result["deleted"]

        print("-" * 70)
        print(f"  {'TOTAL':.<30} {total_deleted:>6} rows deleted")
        print()
        print("✓ Successfully cleared all wargame data.")
        print("=" * 70)

        # Verify deletion
        print("\nVerifying deletion...")
        remaining = 0
        for table in tables:
            count = await count_table_rows(conn, table, guild_id)
            if count > 0:
                print(f"  Warning: {table} still has {count} rows", file=sys.stderr)
                remaining += count

        if remaining == 0:
            print("  All data successfully removed.")
        else:
            print(f"\n  Warning: {remaining} rows still remain.", file=sys.stderr)

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
