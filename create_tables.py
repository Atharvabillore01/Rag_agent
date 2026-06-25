"""One-time script to create all database tables.

Run once before starting the app for the first time:
    python create_tables.py
"""

import asyncio
import sys


async def main():
    from src.db.models import Base
    from src.db.session import engine

    print("Connecting to database...")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("All tables created successfully.")
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
