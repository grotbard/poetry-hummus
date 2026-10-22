"""Mark accounts' phones verified without sending an SMS.

An operator escape hatch for before SMS delivery is configured, and for
support cases where someone cannot receive a code. Every change is written to
the activity log, so a manually verified account is never indistinguishable
from one that passed a real code.

    python scripts/mark_phone_verified.py a@example.com=052-8498629 b@example.com

An entry with no number flips the flag and leaves the phone untouched.
"""

import asyncio
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.db import get_db_handler  # noqa: E402
from app.models import User  # noqa: E402
from app.phone import InvalidPhoneNumber, display_phone, normalise_phone  # noqa: E402
from app.services import log_activity  # noqa: E402


def parse(argument: str) -> tuple[str, str | None]:
    email, _, raw_phone = argument.partition("=")
    return email.strip().lower(), (raw_phone.strip() or None)


async def main(arguments: list[str]) -> int:
    if not arguments:
        print(__doc__)
        return 2

    targets = [parse(a) for a in arguments]
    handler = get_db_handler()
    print(f"Database: {handler.config.safe_url}\n")
    failures = 0

    async with handler.session() as db:
        for email, raw_phone in targets:
            user = (
                await db.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if user is None:
                print(f"  ✗ {email}: no such account")
                failures += 1
                continue

            phone = user.phone
            if raw_phone:
                try:
                    phone = normalise_phone(raw_phone)
                except InvalidPhoneNumber as exc:
                    print(f"  ✗ {email}: {exc}")
                    failures += 1
                    continue

                clash = (
                    await db.execute(
                        select(User).where(User.phone == phone, User.id != user.id)
                    )
                ).scalar_one_or_none()
                if clash is not None:
                    print(f"  ✗ {email}: {phone} already belongs to {clash.email}")
                    failures += 1
                    continue
                user.phone = phone

            user.phone_verified_at = datetime.now(timezone.utc)
            await log_activity(
                db,
                "phone.verified",
                user_id=user.id,
                details={"via": "manual", "phone_set": bool(raw_phone)},
            )
            shown = display_phone(phone) if phone else "(no number)"
            print(f"  ✓ {email}: verified, phone {shown}")

        await db.commit()

    await handler.dispose()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
