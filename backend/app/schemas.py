from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import CoinTxKind, OrderStatus, PaymentStatus, UserRole


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------


class AdminLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserOut(ORMModel):
    id: int
    email: str
    full_name: str
    picture_url: str | None
    phone: str | None
    role: UserRole
    is_active: bool
    coin_balance: int
    lifetime_coins_earned: int
    created_at: datetime
    last_login_at: datetime | None


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=40)


# ---------- Menu ----------


class MenuItemOut(ORMModel):
    id: int
    name_he: str
    name_en: str
    description_he: str
    category: str
    price_agorot: int
    emoji: str
    image_url: str | None
    is_available: bool
    is_vegan: bool
    sort_order: int


class MenuCategoryOut(ORMModel):
    id: int
    key: str
    label_he: str
    sort_order: int


class ReorderRequest(BaseModel):
    """Ordered list of ids; position in the list becomes the new sort order."""

    ids: list[int] = Field(min_length=1)


class MenuItemIn(BaseModel):
    name_he: str = Field(min_length=1, max_length=200)
    name_en: str = ""
    description_he: str = ""
    category: str = "other"
    price_agorot: int = Field(ge=0)
    emoji: str = ""
    is_available: bool = True
    is_vegan: bool = False
    sort_order: int = 100


class MenuItemPatch(BaseModel):
    name_he: str | None = Field(default=None, max_length=200)
    name_en: str | None = None
    description_he: str | None = None
    category: str | None = None
    price_agorot: int | None = Field(default=None, ge=0)
    emoji: str | None = None
    image_url: str | None = None
    is_available: bool | None = None
    is_vegan: bool | None = None
    sort_order: int | None = None


# ---------- Orders ----------


class CartLine(BaseModel):
    menu_item_id: int
    quantity: int = Field(ge=1, le=50)


class OrderCreate(BaseModel):
    items: list[CartLine] = Field(min_length=1)
    note: str = Field(default="", max_length=1000)
    # Coins the member wants to spend on this order (100 coins = 10 ILS).
    redeem_coins: int = Field(default=0, ge=0)


class OrderItemOut(ORMModel):
    id: int
    menu_item_id: int | None
    name_snapshot: str
    unit_price_agorot: int
    quantity: int
    line_total_agorot: int


class OrderOut(ORMModel):
    id: int
    order_number: str
    status: OrderStatus
    payment_status: PaymentStatus
    subtotal_agorot: int
    discount_agorot: int
    total_agorot: int
    coins_spent: int
    coins_earned: int
    note: str
    created_at: datetime
    collected_at: datetime | None
    items: list[OrderItemOut]


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


# ---------- Coins / rewards ----------


class CoinTransactionOut(ORMModel):
    id: int
    amount: int
    kind: CoinTxKind
    balance_after: int
    reason: str
    order_id: int | None
    created_at: datetime


class RewardOut(ORMModel):
    id: int
    name_he: str
    description_he: str
    cost_coins: int
    emoji: str
    is_active: bool


class CoinAdjust(BaseModel):
    amount: int = Field(description="Positive credits, negative debits")
    reason: str = Field(min_length=1, max_length=300)


# ---------- Admin ----------


class AdminUserRow(ORMModel):
    id: int
    email: str
    full_name: str
    picture_url: str | None
    phone: str | None
    role: UserRole
    is_active: bool
    coin_balance: int
    lifetime_coins_earned: int
    created_at: datetime
    last_login_at: datetime | None
    order_count: int = 0
    total_spent_agorot: int = 0


class ActivityLogOut(ORMModel):
    id: int
    user_id: int | None
    action: str
    details: dict
    created_at: datetime


class AdminStats(BaseModel):
    total_members: int
    total_orders: int
    orders_today: int
    revenue_agorot: int
    revenue_today_agorot: int
    coins_outstanding: int
    coins_issued: int
    coins_redeemed: int
    active_orders: int


T = TypeVar("T")


class Paginated(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
