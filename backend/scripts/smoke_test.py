"""End-to-end smoke test of the HTTP API.

Drives the real FastAPI app through every member and admin endpoint.
Defaults to a throwaway SQLite file; point DATABASE_URL at Postgres to run
the identical flow against the production engine.
"""

import asyncio
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./smoke.db")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("SECRET_KEY", "smoke-test-secret")
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "admin@hummushameshorer.com")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "smoke-admin-pw")

import httpx  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, CoinTxKind, User, UserRole  # noqa: E402
from app.security import create_session_token  # noqa: E402
from app.seed import seed_all  # noqa: E402
from app.services import record_coins  # noqa: E402

PASS, FAIL = [], []


def check(label: str, condition: bool, detail: str = "") -> None:
    (PASS if condition else FAIL).append(label)
    mark = "\033[32m✓\033[0m" if condition else "\033[31m✗\033[0m"
    print(f"  {mark} {label}" + (f"  → {detail}" if detail and not condition else ""))


async def main() -> int:
    print(f"\nDatabase: {settings.database_url}\n")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as db:
        await seed_all(db)

    # Create a member directly; the Google flow can't run headless.
    async with SessionLocal() as db:
        member = User(
            email="poet@example.com",
            full_name="בועז המשורר",
            google_sub="smoke-sub-1",
            role=UserRole.member,
        )
        db.add(member)
        await db.flush()
        await record_coins(db, member, 500, CoinTxKind.signup_bonus, reason="smoke bonus")
        await db.commit()
        member_token = create_session_token(member)
        member_id = member.id

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=30
    ) as client:
        member_auth = {"Authorization": f"Bearer {member_token}"}

        print("Public endpoints")
        r = await client.get("/api/health")
        check("health returns ok", r.status_code == 200 and r.json()["status"] == "ok")

        r = await client.get("/api/auth/config")
        check("auth config exposes google flag", "google_enabled" in r.json())

        r = await client.get("/api/menu")
        menu = r.json()
        check("menu seeded", r.status_code == 200 and len(menu) >= 15, f"{len(menu)} items")
        check("menu is Hebrew", any("חומוס" in m["name_he"] for m in menu))

        r = await client.get("/api/rewards")
        rewards = r.json()
        check("rewards seeded", len(rewards) >= 5, f"{len(rewards)} rewards")

        print("\nAuthentication")
        r = await client.get("/api/orders")
        check("anonymous blocked from orders", r.status_code == 401)

        r = await client.get("/api/admin/stats")
        check("anonymous blocked from admin", r.status_code == 401)

        r = await client.get("/api/auth/me", headers=member_auth)
        check("member session works", r.status_code == 200 and r.json()["id"] == member_id)
        check("signup bonus credited", r.json()["coin_balance"] == 500)

        r = await client.get("/api/admin/stats", headers=member_auth)
        check("member blocked from admin (403)", r.status_code == 403)

        r = await client.post(
            "/api/auth/admin/login",
            json={"email": "admin@hummushameshorer.com", "password": "wrong"},
        )
        check("bad admin password rejected", r.status_code == 401)

        r = await client.post(
            "/api/auth/admin/login",
            json={"email": "admin@hummushameshorer.com", "password": "smoke-admin-pw"},
        )
        check("bootstrap admin can log in", r.status_code == 200, r.text[:120])
        admin_cookie = {settings.session_cookie_name: r.cookies.get(settings.session_cookie_name, "")}
        check("admin login sets session cookie", bool(admin_cookie[settings.session_cookie_name]))
        # httpx keeps a cookie jar; left in place it would attach the admin
        # session to member requests, which take cookie over Bearer.
        client.cookies.clear()

        print("\nOrdering and coins")
        hummus = next(m for m in menu if m["name_he"] == "חומוס המשורר")
        pita = next(m for m in menu if m["name_he"] == "פיתה חמה")

        r = await client.get(
            f"/api/coins/redeemable?subtotal_agorot={hummus['price_agorot']}",
            headers=member_auth,
        )
        preview = r.json()
        check("redeem preview caps at half the bill",
              preview["max_coins"] == (hummus["price_agorot"] // 2) // 10,
              str(preview))

        r = await client.post(
            "/api/orders",
            headers=member_auth,
            json={
                "items": [
                    {"menu_item_id": hummus["id"], "quantity": 2},
                    {"menu_item_id": pita["id"], "quantity": 1},
                ],
                "note": "בלי בצל בבקשה",
                "redeem_coins": 100,
            },
        )
        check("order created", r.status_code == 201, r.text[:200])
        order = r.json()
        expected_subtotal = hummus["price_agorot"] * 2 + pita["price_agorot"]
        check("subtotal correct", order["subtotal_agorot"] == expected_subtotal)
        check("discount applied", order["discount_agorot"] == 1000)
        check("total = subtotal - discount",
              order["total_agorot"] == expected_subtotal - 1000)
        check("order number formatted", order["order_number"].startswith("PH-"),
              order["order_number"])

        r = await client.get("/api/auth/me", headers=member_auth)
        check("coins debited on redemption", r.json()["coin_balance"] == 400,
              str(r.json()["coin_balance"]))

        r = await client.post(
            "/api/orders",
            headers=member_auth,
            json={"items": [{"menu_item_id": hummus["id"], "quantity": 1}],
                  "redeem_coins": 99999},
        )
        check("over-redemption rejected", r.status_code == 400)

        r = await client.post(
            "/api/orders", headers=member_auth,
            json={"items": [{"menu_item_id": 99999, "quantity": 1}]},
        )
        check("unknown menu item rejected", r.status_code == 400)

        r = await client.post("/api/orders", headers=member_auth, json={"items": []})
        check("empty cart rejected", r.status_code == 422)

        print("\nAdmin: order lifecycle")
        for target, label in [
            ("preparing", "pending → preparing"),
            ("ready", "preparing → ready"),
            ("collected", "ready → collected"),
        ]:
            r = await client.patch(
                f"/api/admin/orders/{order['id']}/status",
                cookies=admin_cookie,
                json={"status": target},
            )
            check(label, r.status_code == 200, r.text[:150])
            updated = r.json() if r.status_code == 200 else {}

        check("coins awarded on collection",
              updated.get("coins_earned") == (order["total_agorot"] // 100),
              str(updated.get("coins_earned")))
        check("marked paid on collection", updated.get("payment_status") == "paid")

        r = await client.patch(
            f"/api/admin/orders/{order['id']}/status",
            cookies=admin_cookie, json={"status": "cancelled"},
        )
        check("terminal order can't change again", r.status_code == 400)

        r = await client.get("/api/auth/me", headers=member_auth)
        balance_after_earn = r.json()["coin_balance"]
        check("earned coins credited once",
              balance_after_earn == 400 + (order["total_agorot"] // 100),
              str(balance_after_earn))

        print("\nMember cancellation refunds coins")
        r = await client.post(
            "/api/orders", headers=member_auth,
            json={"items": [{"menu_item_id": hummus["id"], "quantity": 1}],
                  "redeem_coins": 200},
        )
        second = r.json()
        check("second order created", r.status_code == 201, r.text[:150])
        r = await client.post(f"/api/orders/{second['id']}/cancel", headers=member_auth)
        check("member can cancel pending order", r.status_code == 200, r.text[:150])
        r = await client.get("/api/auth/me", headers=member_auth)
        check("redeemed coins refunded on cancel",
              r.json()["coin_balance"] == balance_after_earn,
              str(r.json()["coin_balance"]))

        print("\nRewards")
        cheap = min(rewards, key=lambda x: x["cost_coins"])
        r = await client.post(f"/api/rewards/{cheap['id']}/redeem", headers=member_auth)
        check("reward redeemed", r.status_code == 200, r.text[:150])
        check("voucher code issued", r.json().get("voucher_code", "").startswith("RW-"))

        expensive = max(rewards, key=lambda x: x["cost_coins"])
        bal = (await client.get("/api/auth/me", headers=member_auth)).json()["coin_balance"]
        if expensive["cost_coins"] > bal:
            r = await client.post(f"/api/rewards/{expensive['id']}/redeem", headers=member_auth)
            check("unaffordable reward rejected", r.status_code == 400)

        print("\nAdmin: oversight")
        r = await client.get("/api/admin/stats", cookies=admin_cookie)
        stats = r.json() if r.status_code == 200 else {}
        check("stats returned", r.status_code == 200, r.text[:150])
        check("counts members", stats.get("total_members", 0) >= 1)
        check("tracks revenue", stats.get("revenue_agorot", 0) > 0, str(stats))
        check("tracks outstanding coins", stats.get("coins_outstanding", 0) > 0)
        check("tracks redemptions", stats.get("coins_redeemed", 0) > 0)

        r = await client.get("/api/admin/users", cookies=admin_cookie)
        users = r.json()
        check("user list returned", r.status_code == 200 and users["total"] >= 2)
        row = next(u for u in users["items"] if u["id"] == member_id)
        check("per-user order count aggregated", row["order_count"] >= 2, str(row["order_count"]))
        check("per-user spend aggregated", row["total_spent_agorot"] > 0,
              str(row["total_spent_agorot"]))

        r = await client.get("/api/admin/users?q=poet", cookies=admin_cookie)
        check("user search works", any(u["id"] == member_id for u in r.json()["items"]))

        r = await client.get(f"/api/admin/users/{member_id}", cookies=admin_cookie)
        detail = r.json()
        check("user detail has orders", len(detail["orders"]) >= 2)
        check("user detail has coin ledger", len(detail["coin_transactions"]) >= 4)
        check("user detail has activity", len(detail["activity"]) >= 2)

        r = await client.post(
            f"/api/admin/users/{member_id}/coins",
            cookies=admin_cookie,
            json={"amount": 250, "reason": "פיצוי על המתנה"},
        )
        check("admin can credit coins", r.status_code == 200, r.text[:150])
        credited = r.json()["coin_balance"]

        r = await client.post(
            f"/api/admin/users/{member_id}/coins",
            cookies=admin_cookie, json={"amount": -999999, "reason": "overdraft"},
        )
        check("admin overdraft blocked", r.status_code == 400)

        r = await client.get("/api/admin/activity", cookies=admin_cookie)
        check("activity log populated", r.json()["total"] >= 5, str(r.json()["total"]))
        actions = {a["action"] for a in r.json()["items"]}
        check("logs order creation", "order.created" in actions, str(actions))
        check("logs admin adjustment", "admin.coins_adjusted" in actions, str(actions))

        r = await client.get("/api/admin/activity?action=order.created", cookies=admin_cookie)
        check("activity filter works",
              all(a["action"] == "order.created" for a in r.json()["items"]))

        r = await client.get("/api/admin/menu", cookies=admin_cookie)
        check("admin menu includes unavailable", len(r.json()) >= len(menu))

        r = await client.patch(
            f"/api/admin/menu/{pita['id']}", cookies=admin_cookie,
            json={"price_agorot": 700},
        )
        check("admin can edit price", r.status_code == 200 and r.json()["price_agorot"] == 700)

        r = await client.patch(
            f"/api/admin/menu/{pita['id']}", cookies=admin_cookie,
            json={"is_available": False},
        )
        check("admin can hide item", r.json()["is_available"] is False)
        r = await client.get("/api/menu")
        check("hidden item gone from public menu",
              all(m["id"] != pita["id"] for m in r.json()))

        r = await client.post(
            f"/api/admin/users/{member_id}/toggle-active", cookies=admin_cookie
        )
        check("admin can disable member", r.status_code == 200 and r.json()["is_active"] is False)
        r = await client.get("/api/auth/me", headers=member_auth)
        check("disabled member loses access", r.status_code == 401)
        await client.post(f"/api/admin/users/{member_id}/toggle-active", cookies=admin_cookie)

        print("\nLedger integrity")
        async with SessionLocal() as db:
            from sqlalchemy import func, select
            from app.models import CoinTransaction

            ledger = (
                await db.execute(
                    select(func.coalesce(func.sum(CoinTransaction.amount), 0)).where(
                        CoinTransaction.user_id == member_id
                    )
                )
            ).scalar()
            cached = (await db.get(User, member_id)).coin_balance
            check("ledger sum == cached balance", ledger == cached, f"{ledger} vs {cached}")
            check("balance matches last admin credit", cached == credited, f"{cached} vs {credited}")

    await engine.dispose()

    print(f"\n{'─' * 54}")
    print(f"  passed: {len(PASS)}   failed: {len(FAIL)}")
    if FAIL:
        print("\n  failures:")
        for f in FAIL:
            print(f"    • {f}")
    print()
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
