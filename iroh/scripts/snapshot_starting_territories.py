#!/usr/bin/env python3
"""
Snapshot current territory counts as starting territory counts for all factions in a guild.

Usage:
    python snapshot_starting_territories.py <guild_id>

Example:
    python snapshot_starting_territories.py 1234567890
"""
import asyncio
import asyncpg
import sys


async def main():
    """Main function to snapshot starting territory counts."""
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

    conn = await asyncpg.connect(
        host='db',
        port=5432,
        user='AVATAR',
        password='password',
        database='AVATAR'
    )

    try:
        print(f"Snapshotting starting territory counts for guild ID: {guild_id}")
        print("=" * 60)

        # Fetch all factions
        factions = await conn.fetch(
            "SELECT id, faction_id, name FROM Faction WHERE guild_id = $1 ORDER BY faction_id;",
            guild_id
        )

        if not factions:
            print("No factions found for this guild.")
            return

        # Count territories for each faction
        results = []
        for faction in factions:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM Territory WHERE controller_faction_id = $1 AND guild_id = $2;",
                faction['id'], guild_id
            )
            results.append((faction['id'], faction['faction_id'], faction['name'], count))

        # Display summary
        print(f"\nFound {len(results)} factions:\n")
        for _, faction_id, name, count in results:
            print(f"  {name} ({faction_id}): {count} territories")

        # Confirm
        response = input(f"\nSet these as starting territory counts? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Cancelled.")
            return

        # Update each faction
        for internal_id, faction_id, name, count in results:
            await conn.execute(
                "UPDATE Faction SET starting_territory_count = $1 WHERE id = $2;",
                count, internal_id
            )
            print(f"  Set {name} ({faction_id}) starting_territory_count = {count}")

        print(f"\nDone. Updated {len(results)} factions.")
        print("=" * 60)

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
