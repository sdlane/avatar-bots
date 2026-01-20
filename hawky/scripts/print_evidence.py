"""
Script to print all evidence from the database.

Usage:
    python print_evidence.py
"""

import asyncio
import asyncpg
import sys
from pathlib import Path

# Handle direct execution
if __name__ == "__main__":
    scripts_dir = Path(__file__).parent
    hawky_dir = scripts_dir.parent
    avatar_bots_dir = hawky_dir.parent
    sys.path.insert(0, str(scripts_dir))
    sys.path.insert(0, str(hawky_dir))
    sys.path.insert(0, str(avatar_bots_dir))

from db import Evidence

DB_URL = "postgresql://AVATAR:password@db:5432/AVATAR"


async def print_evidence(conn: asyncpg.Connection):
    """Print all evidence entries."""
    evidence_list = await Evidence.fetch_all(conn)
    print("=" * 60)
    print(f"EVIDENCE ({len(evidence_list)} total)")
    print("=" * 60)
    for evidence in evidence_list:
        print(f"  [{evidence.analysis_number}]")
        print(f"      Hint: {evidence.hint}")
        print(f"      GM Notes: {evidence.gm_notes}")
        print()


async def main():
    """Main entry point."""
    conn = await asyncpg.connect(DB_URL)

    try:
        await print_evidence(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
