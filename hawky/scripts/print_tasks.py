#!/usr/bin/env python3
"""
Script to print all tasks from the HawkyTask table.
"""
import asyncio
import sys
import os

# Add parent directories to the path so we can import db modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import asyncpg
from db.hawky_task import HawkyTask


async def main():
    """Connect to the database and print all tasks."""
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
    try:
        await HawkyTask.print_all(conn)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
