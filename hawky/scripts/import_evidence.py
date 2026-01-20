"""
Script to import evidence data from a CSV file.

Usage:
    python import_evidence.py <csv_filename>

CSV format:
    Analysis Number,Hint,GM Notes
"""

import asyncio
import asyncpg
import csv
import logging
import sys
from pathlib import Path

# Handle both direct execution and module import
if __name__ == "__main__":
    # Add parent directories to path for direct execution
    # Script is in hawky/scripts/
    scripts_dir = Path(__file__).parent
    hawky_dir = scripts_dir.parent
    avatar_bots_dir = hawky_dir.parent
    sys.path.insert(0, str(scripts_dir))
    sys.path.insert(0, str(hawky_dir))
    sys.path.insert(0, str(avatar_bots_dir))

from db import Evidence

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - ImportEvidence - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_URL = "postgresql://AVATAR:password@db:5432/AVATAR"


def load_evidence_from_csv(filename: str) -> list[Evidence]:
    """
    Load evidence entries from a CSV file.

    Expected columns: Analysis Number, Hint, GM Notes
    """
    evidence_list = []

    with open(filename, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            evidence = Evidence(
                analysis_number=row['Analysis Number'].strip(),
                hint=row['Hint'].strip(),
                gm_notes=row['GM Notes'].strip() if row['GM Notes'] else ""
            )
            evidence_list.append(evidence)

    return evidence_list


async def import_evidence_data(conn: asyncpg.Connection, filename: str):
    """
    Import evidence data from the specified CSV file.
    Clears existing data before importing.
    """
    logger.info("Clearing existing evidence data...")
    await Evidence.delete_all(conn)

    logger.info(f"Loading evidence from {filename}...")
    evidence_list = load_evidence_from_csv(filename)

    logger.info(f"Inserting {len(evidence_list)} evidence entries...")
    for evidence in evidence_list:
        await evidence.upsert(conn)

    logger.info("Evidence data import complete!")


async def main():
    """
    Main entry point for the import script.
    """
    if len(sys.argv) != 2:
        print("Usage: python import_evidence.py <csv_filename>")
        print("\nCSV format:")
        print("  analysis_number,hint,gm_notes")
        sys.exit(1)

    csv_filename = sys.argv[1]

    if not Path(csv_filename).exists():
        print(f"Error: File '{csv_filename}' not found")
        sys.exit(1)

    logger.info("Connecting to database...")
    conn = await asyncpg.connect(DB_URL)

    try:
        await import_evidence_data(conn, csv_filename)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
