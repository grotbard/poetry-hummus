# חומוס המשורר — אפליקציית מועדון לקוחות

Club-member web app for **Hummus Hameshorer** (The Poet's Hummus), Even Gvirol / Bitzaron, Tel Aviv.
Members sign in with Google, order from the menu, and earn **Poet Coins** (מטבעות משורר) —
a chickpea-based loyalty currency in the McDonald's-rewards mould.

## Stack

| Layer | Choice |
|---|---|
| Backend | Python · FastAPI · **SQLAlchemy 2.0** (async ORM) · Alembic |
| Database | PostgreSQL (via asyncpg) |
| Frontend | React 18 + TypeScript + Vite + Tailwind, Hebrew RTL |
| Auth | Google OAuth 2.0 (server-side code flow) → httpOnly JWT cookie |
| Admin auth | Separate email + bcrypt password login, admin-only |

## Getting started

```bash
./setup.sh                  # venv + backend deps + frontend deps + .env
# then edit backend/.env (Google credentials, admin password)
docker compose up -d db     # Postgres on port 5433
cd backend  && .venv/bin/uvicorn app.main:app --reload
cd frontend && npm run dev  # → http://localhost:5173
```

Full instructions, including how to create the Google OAuth client:
**[docs/SETUP.md](docs/SETUP.md)**.

## Poet Coins (מטבעות משורר)

The chickpea is the coin. Rules live in `backend/app/services.py` and are tunable by env var:

- **Earning** — `COINS_PER_SHEKEL` (default 1) coin per ₪1, credited when an order
  reaches `collected`, never before. `coins_awarded` makes that award idempotent.
- **Signup bonus** — `SIGNUP_BONUS_COINS` (default 20) on first Google sign-in.
- **Redemption** — 1 coin = 10 agorot, i.e. 100 coins = ₪10.
- **Redemption cap** — at most 50% of any single bill (`MAX_REDEEM_FRACTION`),
  so every order still takes some cash.
- **Cancellation** — coins spent on a cancelled order are refunded; refunds do not
  inflate `lifetime_coins_earned`.
- **Rewards catalogue** — fixed-price perks (free pita → meal for two) redeemed for a voucher code.

Every movement is an append-only row in `coin_transactions` carrying `amount`,
`kind`, `balance_after` and a reason. `users.coin_balance` is a cached running total;
the ledger is the source of truth and the two are asserted equal in tests.

## What the admin can see and do

- **Overview** — members, active orders, orders/revenue today and all-time,
  coins outstanding (with the shekel liability), issued vs redeemed with a redemption rate.
- **Orders** — live queue, filter by status, advance pending → preparing → ready →
  collected (which captures payment and awards coins), or cancel.
- **Members** — searchable table with per-member order count and lifetime spend;
  click through to a full card: profile, orders, coin ledger, activity.
- **Coin adjustments** — manual credit/debit with a mandatory reason, written to the audit log.
- **Block/unblock** a member (self-disable is refused); blocked members lose access immediately.
- **Activity log** — logins, registrations, orders, status changes, redemptions and admin
  actions, filterable by type and time window.
- **Menu** — add items, upload a photo per item, reorder groups and items with ▲▼,
  edit prices and toggle availability live.
  Deleting removes an item outright if it was never ordered; one with order history is
  retired (hidden) instead, so past orders keep their link. Order lines also snapshot
  name + price, so history survives any menu change.

Item photos are validated by magic bytes (JPEG/PNG/GIF/WebP, max 4MB — SVG is refused
since it can carry script), stored under `backend/media/` and served at `/media`.
Replacing or deleting an image removes the old file.

## Data model

`users` · `menu_categories` · `menu_items` · `orders` · `order_items` · `rewards` ·
`coin_transactions` · `activity_log`

Display order is data, not code: `menu_categories.sort_order` orders the groups and
`menu_items.sort_order` orders items within a group, both editable from the admin UI.
An item whose category has no row sorts last rather than vanishing.

Money is stored in agorot (integers) throughout — no floats. Enums are persisted by value.

## Tests

```bash
cd backend
.venv/bin/python -m pytest -q              # 35 unit tests: ledger, menu admin, ordering
.venv/bin/python scripts/smoke_test.py     # 62 end-to-end API checks
cd ../frontend && npm run typecheck && npm run build
```

`scripts/smoke_test.py` drives the real ASGI app end to end. It defaults to a throwaway
SQLite file; set `DATABASE_URL` to a Postgres URL to run the identical flow there.

To fill the admin dashboard with something to look at:

```bash
cd backend && .venv/bin/python scripts/seed_demo.py   # 6 members, ~24 orders, coin history
```

## Brand

Logo and palette are taken from the restaurant's own profile artwork
(`assets/logo-original.jpg`): teal `#7CC4C4`, wine `#67062F`, hummus cream `#E8DCA0`,
chickpea gold `#D9A94C`.
