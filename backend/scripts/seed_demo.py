"""Populate the database with demo members, orders and coin history.

Development aid only — gives the admin dashboard something to show.
"""

import asyncio
import pathlib
import random
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.db import get_db_handler  # noqa: E402
from app.models import (  # noqa: E402
    CoinTxKind,
    MenuItem,
    OrderStatus,
    User,
    UserRole,
)
from app.services import advance_order_status, create_order, record_coins  # noqa: E402

MEMBERS = [
    ("boaz@example.com", "בועז חזן", "052-8498629"),
    ("yael@example.com", "יעל ברקוביץ'", "054-1112233"),
    ("omer@example.com", "עומר לוי", "050-9876543"),
    ("noa@example.com", "נועה שמש", "053-4445566"),
    ("itay@example.com", "איתי כהן", None),
    ("maya@example.com", "מאיה אזולאי", "058-7778899"),
]

NOTES = ["בלי בצל בבקשה", "", "חריף מאוד", "", "לקחת, לא לשבת", ""]


async def main() -> None:
    random.seed(7)
    handler = get_db_handler()
    async with handler.session() as db:
        menu = (
            await db.execute(select(MenuItem).where(MenuItem.is_available.is_(True)))
        ).scalars().all()
        if not menu:
            print("No menu items — start the API once to seed the menu first.")
            return

        created = 0
        for i, (email, name, phone) in enumerate(MEMBERS):
            existing = (
                await db.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if existing:
                continue

            user = User(
                email=email,
                full_name=name,
                phone=phone,
                google_sub=f"demo-sub-{i}",
                role=UserRole.member,
                created_at=datetime.now(timezone.utc) - timedelta(days=60 - i * 7),
                last_login_at=datetime.now(timezone.utc) - timedelta(hours=i * 5),
            )
            db.add(user)
            await db.flush()
            await record_coins(
                db, user, 20, CoinTxKind.signup_bonus, reason="בונוס הרשמה למועדון"
            )
            created += 1

            # A history of collected orders, plus some still in the queue.
            for n in range(random.randint(2, 6)):
                lines = [
                    (random.choice(menu).id, random.randint(1, 2))
                    for _ in range(random.randint(1, 3))
                ]
                redeem = 0
                if user.coin_balance > 150 and random.random() < 0.4:
                    redeem = min(100, user.coin_balance // 2)

                order = await create_order(
                    db, user, lines, random.choice(NOTES), redeem
                )
                order.created_at = datetime.now(timezone.utc) - timedelta(
                    days=random.randint(0, 45), hours=random.randint(0, 20)
                )

                roll = random.random()
                if roll < 0.7:
                    for state in (
                        OrderStatus.preparing,
                        OrderStatus.ready,
                        OrderStatus.collected,
                    ):
                        await advance_order_status(db, order, state)
                elif roll < 0.8:
                    await advance_order_status(db, order, OrderStatus.preparing)
                elif roll < 0.88:
                    await advance_order_status(db, order, OrderStatus.ready)
                elif roll < 0.94:
                    await advance_order_status(db, order, OrderStatus.cancelled)
                # else: leave it pending

        await db.commit()
        print(f"Seeded {created} demo members with orders and coin history.")

    await handler.dispose()


if __name__ == "__main__":
    asyncio.run(main())
