#!/usr/bin/env python3
"""
Print unique guild IDs from wargame-related database tables.
Excludes the Character table as requested.
"""
import asyncio
import asyncpg
import sys
from pathlib import Path

# Add parent directory to path for imports
parent_dir = Path(__file__).parent
sys.path.insert(0, str(parent_dir))


# Wargame-related tables with guild_id column (excluding Character)
WARGAME_TABLES = [
    'Faction',
    'FactionMember',
    'FactionJoinRequest',
    'Territory',
    'TerritoryAdjacency',
    'Unit',
    'UnitType',
    'PlayerResources',
    'WargameConfig',
    'TurnLog',
    'WargameOrder'
]


async def get_guild_ids_from_table(conn: asyncpg.Connection, table_name: str) -> set[int]:
    """Fetch unique guild_id values from a table."""
    query = f"SELECT DISTINCT guild_id FROM {table_name} WHERE guild_id IS NOT NULL;"
    try:
        rows = await conn.fetch(query)
        return {row['guild_id'] for row in rows}
    except Exception as e:
        print(f"Warning: Could not query {table_name}: {e}", file=sys.stderr)
        return set()


async def main():
    """Main function to connect to database and print guild IDs."""
    # Database connection parameters (from conftest.py)
    conn = await asyncpg.connect(
        host='db',
        port=5432,
        user='AVATAR',
        password='password',
        database='AVATAR'
    )

    try:
        print("Scanning wargame-related tables for unique guild IDs...")
        print("=" * 60)

        all_guild_ids = set()
        table_guild_ids = {}

        for table_name in WARGAME_TABLES:
            guild_ids = await get_guild_ids_from_table(conn, table_name)
            table_guild_ids[table_name] = guild_ids
            all_guild_ids.update(guild_ids)

            if guild_ids:
                print(f"\n{table_name}:")
                for guild_id in sorted(guild_ids):
                    print(f"  - {guild_id}")
            else:
                print(f"\n{table_name}: (no guild IDs found)")

        print("\n" + "=" * 60)
        print("\nSUMMARY - All unique guild IDs across wargame tables:")
        print("=" * 60)

        if all_guild_ids:
            for guild_id in sorted(all_guild_ids):
                # Count how many tables contain this guild_id
                table_count = sum(1 for guild_ids in table_guild_ids.values() if guild_id in guild_ids)
                print(f"  {guild_id} (present in {table_count} table(s))")
        else:
            print("  (no guild IDs found in any wargame tables)")

        print()

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
