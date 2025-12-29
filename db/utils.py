import asyncpg
import logging

logger = logging.getLogger(__name__)

async def inspect_database():
    # Connect to your database (use your own credentials or env vars)
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")

    # --- Step 1: Get list of tables ---
    tables = await conn.fetch("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)

    logger.info("📋 Tables found in database:\n")
    for t in tables:
        table_name = t["table_name"]
        logger.info(f"🧩 {table_name}")

        # --- Step 2: Get columns for each table ---
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = $1
            ORDER BY ordinal_position;
        """, table_name)

        for col in columns:
            col_name = col["column_name"]
            dtype = col["data_type"]
            nullable = col["is_nullable"]
            default = col["column_default"]
            logger.info(f"   • {col_name:<20} {dtype:<15} NULLABLE={nullable:<3} DEFAULT={default}")
        logger.info("")

    await conn.close()
