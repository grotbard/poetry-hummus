from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

# BigInteger autoincrements on Postgres but not on SQLite, which tests use.
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    # JSONB on Postgres, plain JSON elsewhere (sqlite in tests).
    type_annotation_map = {dict: JSON().with_variant(JSONB(), "postgresql")}


class UserRole(str, enum.Enum):
    member = "member"
    admin = "admin"


class OrderStatus(str, enum.Enum):
    pending = "pending"
    preparing = "preparing"
    ready = "ready"
    collected = "collected"
    cancelled = "cancelled"


class PaymentStatus(str, enum.Enum):
    unpaid = "unpaid"
    paid = "paid"
    refunded = "refunded"


class CoinTxKind(str, enum.Enum):
    earn = "earn"
    redeem = "redeem"
    signup_bonus = "signup_bonus"
    admin_adjust = "admin_adjust"
    refund = "refund"


def _enum(e: type[enum.Enum], name: str) -> Enum:
    """Store enums by value (lowercase strings), not by Python member name."""
    return Enum(e, name=name, values_callable=lambda x: [i.value for i in x])


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    google_sub: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, default=None
    )
    # Only set for admins who sign in with email + password.
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)

    full_name: Mapped[str] = mapped_column(String(200), default="")
    picture_url: Mapped[str | None] = mapped_column(Text, default=None)
    phone: Mapped[str | None] = mapped_column(String(40), default=None)

    role: Mapped[UserRole] = mapped_column(
        _enum(UserRole, "user_role"), default=UserRole.member, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Denormalised running balance; the ledger in coin_transactions is the source
    # of truth and must always sum to this value.
    coin_balance: Mapped[int] = mapped_column(Integer, default=0)
    lifetime_coins_earned: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    orders: Mapped[list[Order]] = relationship(back_populates="user")
    coin_transactions: Mapped[list[CoinTransaction]] = relationship(
        back_populates="user", foreign_keys="CoinTransaction.user_id"
    )


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_he: Mapped[str] = mapped_column(String(200))
    name_en: Mapped[str] = mapped_column(String(200), default="")
    description_he: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(60), index=True, default="other")
    # Prices are stored in agorot (1/100 ILS) to avoid float money.
    price_agorot: Mapped[int] = mapped_column(Integer)
    emoji: Mapped[str] = mapped_column(String(16), default="")
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_vegan: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[OrderStatus] = mapped_column(
        _enum(OrderStatus, "order_status"), default=OrderStatus.pending, index=True
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        _enum(PaymentStatus, "payment_status"), default=PaymentStatus.unpaid
    )
    payment_reference: Mapped[str | None] = mapped_column(String(100), default=None)

    subtotal_agorot: Mapped[int] = mapped_column(Integer, default=0)
    discount_agorot: Mapped[int] = mapped_column(Integer, default=0)
    total_agorot: Mapped[int] = mapped_column(Integer, default=0)

    coins_spent: Mapped[int] = mapped_column(Integer, default=0)
    coins_earned: Mapped[int] = mapped_column(Integer, default=0)
    # Guards against awarding earn-coins twice for one order.
    coins_awarded: Mapped[bool] = mapped_column(Boolean, default=False)

    note: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    collected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    user: Mapped[User] = relationship(back_populates="orders")
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    menu_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("menu_items.id", ondelete="SET NULL"), default=None
    )
    # Snapshot name/price so historical orders survive menu edits.
    name_snapshot: Mapped[str] = mapped_column(String(200))
    unit_price_agorot: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    line_total_agorot: Mapped[int] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="items")


class Reward(Base):
    __tablename__ = "rewards"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_he: Mapped[str] = mapped_column(String(200))
    description_he: Mapped[str] = mapped_column(Text, default="")
    cost_coins: Mapped[int] = mapped_column(Integer)
    emoji: Mapped[str] = mapped_column(String(16), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)


class CoinTransaction(Base):
    """Append-only ledger of every Poet Coin movement."""

    __tablename__ = "coin_transactions"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), default=None, index=True
    )
    reward_id: Mapped[int | None] = mapped_column(
        ForeignKey("rewards.id", ondelete="SET NULL"), default=None
    )
    # Positive = credit, negative = debit.
    amount: Mapped[int] = mapped_column(Integer)
    kind: Mapped[CoinTxKind] = mapped_column(_enum(CoinTxKind, "coin_tx_kind"))
    balance_after: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(300), default="")
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    user: Mapped[User] = relationship(
        back_populates="coin_transactions", foreign_keys=[user_id]
    )


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), default=None, index=True
    )
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    action: Mapped[str] = mapped_column(String(80), index=True)
    details: Mapped[dict] = mapped_column(default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


Index("ix_orders_user_created", Order.user_id, Order.created_at.desc())
Index("ix_cointx_user_created", CoinTransaction.user_id, CoinTransaction.created_at.desc())
