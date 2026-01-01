#!/usr/bin/env python3
"""
Clear turn log data for a specific guild.

Usage:
    python clear_turn_logs.py <guild_id>

Example:
    python clear_turn_logs.py 1234567890
"""
import asyncio
import asyncpg
import sys
from pathlib import Path

# Add parent directory to path for imports
parent_dir = Path(__file__).parent
sys.path.insert(0, str(parent_dir))


async def clear_turn_logs(conn: asyncpg.Connection, guild_id: int) -> int:
    """
    Delete all TurnLog entries for a specific guild.

    Args:
        conn: Database connection
        guild_id: Guild ID to clear logs for

    Returns:
        Number of rows deleted
    """
    # Count entries before deletion
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM TurnLog WHERE guild_id = $1;",
        guild_id
    )

    if count == 0:
        return 0

    # Delete entries
    result = await conn.execute(
        "DELETE FROM TurnLog WHERE guild_id = $1;",
        guild_id
    )

    # Extract number from result string (e.g., "DELETE 42" -> 42)
    deleted_count = int(result.split()[-1]) if result.startswith("DELETE") else 0

    return deleted_count


async def main():
    """Main function to connect to database and clear turn logs."""
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

    # Database connection parameters (from conftest.py)
    conn = await asyncpg.connect(
        host='db',
        port=5432,
        user='AVATAR',
        password='password',
        database='AVATAR'
    )

    try:
        print(f"Clearing turn logs for guild ID: {guild_id}")
        print("=" * 60)

        # Count entries before deletion
        count_before = await conn.fetchval(
            "SELECT COUNT(*) FROM TurnLog WHERE guild_id = $1;",
            guild_id
        )

        print(f"\nFound {count_before} turn log entries for guild {guild_id}")

        if count_before == 0:
            print("Nothing to delete.")
            return

        # Ask for confirmation
        response = input(f"\nAre you sure you want to delete {count_before} entries? (yes/no): ")

        if response.lower() not in ['yes', 'y']:
            print("Cancelled.")
            return

        # Perform deletion
        deleted_count = await clear_turn_logs(conn, guild_id)

        print(f"\n✓ Successfully deleted {deleted_count} turn log entries.")
        print("=" * 60)

        # Verify deletion
        count_after = await conn.fetchval(
            "SELECT COUNT(*) FROM TurnLog WHERE guild_id = $1;",
            guild_id
        )

        if count_after == 0:
            print("Verification: No entries remain for this guild.")
        else:
            print(f"Warning: {count_after} entries still remain (this shouldn't happen).", file=sys.stderr)

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
