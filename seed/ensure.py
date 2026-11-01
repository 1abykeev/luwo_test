"""Load the demo data only when the database has no users yet.

`python -m seed.seed` wipes the demo data, so it must not run on every start. This is what the Docker
entrypoint calls: a second start keeps whatever is already in the database.

    python -m seed.ensure
"""

import asyncio

from sqlalchemy import text

from app.db.session import SessionFactory, engine
from seed.seed import seed


async def main() -> None:
    async with SessionFactory() as session:
        users = (await session.execute(text("select count(*) from users"))).scalar_one()
    if users == 0:
        await seed()
    else:
        print(f"Database already has {users} users: keeping the existing data.")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
