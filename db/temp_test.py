import asyncpg
import asyncio

from server_config import *
from character import *

async def main():
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")

    # Print all entries
    await ServerConfig.print_all(conn)

    # Print all characters
    await Character.print_all(conn)

    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
