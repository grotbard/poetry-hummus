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


class PhoneCodeRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=40)


class PhoneCodeSent(BaseModel):
    ok: bool
    phone: str
    resend_in_seconds: int
    # Present only in development with the mock sender.
    dev_code: str | None = None


class PhoneSignupIn(BaseModel):
    """Phone-first signup: the number plus an email and name."""

    phone: str = Field(min_length=6, max_length=40)
    code: str = Field(min_length=4, max_length=8)
    email: EmailStr
    full_name: str = Field(default="", max_length=200)
    # Optional invite code, as on the Google path.
    ref: str | None = Field(default=None, max_length=16)


class PhoneVerifyIn(BaseModel):
    """Attach a verified number to the signed-in account."""

    phone: str = Field(min_length=6, max_length=40)
    code: str = Field(min_length=4, max_length=8)


class UserOut(ORMModel):
    id: int
    email: str
    full_name: str
    picture_url: str | None
    phone: str | None
    role: UserRole
    is_active: bool
    phone_verified: bool = False
    coin_balance: int
    lifetime_coins_earned: int
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def from_user(cls, user) -> "UserOut":
        row = cls.model_validate(user)
        row.phone_verified = user.phone_verified_at is not None
        return row


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
    allows_egg: bool
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
    allows_egg: bool = False
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
    allows_egg: bool | None = None
    sort_order: int | None = None


# ---------- Orders ----------


class CartLine(BaseModel):
    menu_item_id: int
    quantity: int = Field(ge=1, le=50)
    # Extra hard-boiled eggs on each plate of this line.
    eggs: int = Field(default=0, ge=0, le=10)


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
    eggs: int
    egg_price_agorot: int
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
    coins_pending: int
    feedback_food: int | None
    feedback_service: int | None
    feedback_at: datetime | None
    note: str
    created_at: datetime
    collected_at: datetime | None
    items: list[OrderItemOut]


class AdminOrderOut(OrderOut):
    """An order as the kitchen sees it: who placed it, and how to reach them.

    Separate from OrderOut so customer details never reach member endpoints.
    """

    customer_id: int
    customer_name: str
    customer_email: str
    customer_phone: str | None
    customer_phone_verified: bool


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class FeedbackIn(BaseModel):
    """The whole survey: two 1-5 ratings."""

    food: int = Field(ge=1, le=5, description="How was the hummus?")
    service: int = Field(ge=1, le=5, description="How was the service?")


class FeedbackResult(BaseModel):
    ok: bool
    coins_granted: int
    balance: int
    in_time: bool


# ---------- Coins / rewards ----------


class CoinTransactionOut(ORMModel):
    id: int
    amount: int
    kind: CoinTxKind
    balance_after: int
    reason: str
    order_id: int | None
    created_at: datetime
    expires_at: datetime | None


class InvitedFriend(BaseModel):
    name: str
    joined_at: datetime
    completed: bool
    coins_earned: int


class ReferralSummary(BaseModel):
    """Everything the invite panel needs."""

    code: str
    link: str
    coins_per_friend: int
    friend_bonus_coins: int
    max_friends: int
    completed_count: int
    pending_count: int
    coins_earned: int
    slots_left: int
    friends: list[InvitedFriend]


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
    phone_verified_at: datetime | None
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
