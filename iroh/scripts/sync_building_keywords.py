#!/usr/bin/env python3
"""
Sync building keywords from their building type definitions.

Iterates through all buildings for a guild and updates each building's
keywords to match the keywords defined on its BuildingType.

Usage:
    python sync_building_keywords.py <guild_id>

Example:
    python sync_building_keywords.py 1234567890
"""
import asyncio
import asyncpg
import sys
from pathlib import Path

# Add parent directory to path for imports
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from db import Building, BuildingType


async def main():
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
        buildings = await Building.fetch_all(conn, guild_id)
        if not buildings:
            print(f"No buildings found for guild {guild_id}.")
            return

        # Build a cache of building types
        building_types = {}
        for b in buildings:
            if b.building_type not in building_types:
                bt = await BuildingType.fetch_by_type_id(conn, b.building_type, guild_id)
                building_types[b.building_type] = bt

        # Preview changes
        updates = []
        for b in buildings:
            bt = building_types.get(b.building_type)
            if bt is None:
                print(f"  WARNING: BuildingType '{b.building_type}' not found for building '{b.building_id}', skipping")
                continue

            old_kw = sorted(b.keywords) if b.keywords else []
            new_kw = sorted(bt.keywords) if bt.keywords else []
            if old_kw != new_kw:
                updates.append((b, bt.keywords or []))
                print(f"  {b.building_id}: {old_kw} -> {new_kw}")

        if not updates:
            print(f"\nAll {len(buildings)} buildings already match their building type keywords.")
            return

        print(f"\n{len(updates)} of {len(buildings)} buildings will be updated.")
        response = input("Proceed? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Cancelled.")
            return

        for b, new_keywords in updates:
            b.keywords = new_keywords
            await b.upsert(conn)

        print(f"\nUpdated {len(updates)} buildings.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
