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

from collections import defaultdict
from db import Building, BuildingType, Territory, Faction


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

        # Cache territories and factions for summary
        territories = {}
        factions = {}

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

        # Build summary: faction -> building_type -> count
        # Resolve territory and faction for each updated building
        for b, _ in updates:
            if b.territory_id and b.territory_id not in territories:
                territories[b.territory_id] = await Territory.fetch_by_territory_id(conn, b.territory_id, guild_id)

        for t in territories.values():
            if t and t.controller_faction_id and t.controller_faction_id not in factions:
                factions[t.controller_faction_id] = await Faction.fetch_by_id(conn, t.controller_faction_id)

        # faction_name -> building_type -> count
        counts = defaultdict(lambda: defaultdict(int))
        for b, _ in updates:
            faction_name = "Uncontrolled"
            t = territories.get(b.territory_id) if b.territory_id else None
            if t and t.controller_faction_id:
                faction = factions.get(t.controller_faction_id)
                if faction:
                    faction_name = faction.name
            counts[faction_name][b.building_type] += 1

        print(f"\nUpdated {len(updates)} buildings.\n")
        print("Summary:")
        print("=" * 40)
        for faction_name in sorted(counts):
            print(f"\n  {faction_name}:")
            for btype in sorted(counts[faction_name]):
                print(f"    {btype}: {counts[faction_name][btype]}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
