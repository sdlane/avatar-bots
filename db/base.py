import asyncpg

async def get_conn():
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")
    return conn
