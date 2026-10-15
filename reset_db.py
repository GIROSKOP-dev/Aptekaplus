"""Пересоздать БД: schema.sql + seed."""
import asyncio, sys
from pathlib import Path
import asyncpg
from app.config import DATABASE_URL
import seed

SCHEMA = Path(__file__).parent / "schema.sql"


async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(SCHEMA.read_text(encoding="utf-8"))
        print("✓ схема пересоздана")
    finally:
        await conn.close()
    await seed.main()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())