"""Seed the menu, rewards and bootstrap admin.

Menu reflects Hummus Hameshorer's real offering (hummus plates, salads,
shakshuka, malabi); prices are representative and editable from the admin UI.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models import MenuItem, Reward, User, UserRole
from .security import hash_password

MENU: list[dict] = [
    # --- חומוסים ---
    dict(name_he="חומוס המשורר", name_en="The Poet's Hummus", category="hummus",
         description_he="החומוס של הבית, גרגירים שלמים, שמן זית וזעתר",
         price_agorot=4200, emoji="🫛", is_vegan=True, sort_order=1),
    dict(name_he="חומוס פול", name_en="Hummus Ful", category="hummus",
         description_he="חומוס עם פול חם ברוטב עגבניות",
         price_agorot=4500, emoji="🫛", is_vegan=True, sort_order=2),
    dict(name_he="חומוס מסבחה", name_en="Hummus Masabacha", category="hummus",
         description_he="גרגירים שלמים בטחינה חמה ולימון",
         price_agorot=4500, emoji="🫛", is_vegan=True, sort_order=3),
    dict(name_he="חומוס פטריות", name_en="Mushroom Hummus", category="hummus",
         description_he="חומוס עם פטריות מוקפצות בשום ויין",
         price_agorot=5200, emoji="🍄", is_vegan=True, sort_order=4),
    dict(name_he="חומוס בשר טבעוני", name_en="Vegan Meat Hummus", category="hummus",
         description_he="חומוס עם בשר טבעוני Redefine, צנוברים ופטרוזיליה",
         price_agorot=5900, emoji="🫛", is_vegan=True, sort_order=5),
    dict(name_he="חומוס ביצה", name_en="Hummus with Egg", category="hummus",
         description_he="חומוס עם ביצה קשה וזעתר",
         price_agorot=4600, emoji="🥚", sort_order=6),
    # --- מרקים ושקשוקה ---
    dict(name_he="שקשוקה", name_en="Shakshuka", category="mains",
         description_he="שקשוקה אדומה עם ביצים, לחם הבית בצד",
         price_agorot=5400, emoji="🍳", sort_order=10),
    dict(name_he="מרק עדשים", name_en="Lentil Soup", category="mains",
         description_he="מרק עדשים כתומות עם כמון ולימון",
         price_agorot=3200, emoji="🍲", is_vegan=True, sort_order=11),
    # --- תוספות וסלטים ---
    dict(name_he="סלט ירקות", name_en="Vegetable Salad", category="sides",
         description_he="עגבנייה, מלפפון, בצל ופטרוזיליה בשמן זית",
         price_agorot=2400, emoji="🥗", is_vegan=True, sort_order=20),
    dict(name_he="טחינה", name_en="Tahini", category="sides",
         description_he="טחינה גולמית עם לימון ושום", price_agorot=1200,
         emoji="🥣", is_vegan=True, sort_order=21),
    dict(name_he="חמוצים", name_en="Pickles", category="sides",
         description_he="מנת חמוצים של הבית", price_agorot=900,
         emoji="🥒", is_vegan=True, sort_order=22),
    dict(name_he="פיתה חמה", name_en="Warm Pita", category="sides",
         description_he="פיתה טרייה מהטאבון", price_agorot=600,
         emoji="🫓", is_vegan=True, sort_order=23),
    dict(name_he="פלאפל (5 יח')", name_en="Falafel (5 pcs)", category="sides",
         description_he="חמישה כדורי פלאפל טריים", price_agorot=1500,
         emoji="🧆", is_vegan=True, sort_order=24),
    # --- שתייה ---
    dict(name_he="לימוננה", name_en="Lemonade", category="drinks",
         description_he="לימונענע קרה של הבית", price_agorot=1400,
         emoji="🍋", is_vegan=True, sort_order=30),
    dict(name_he="קולה", name_en="Coca-Cola", category="drinks",
         description_he="פחית 330 מ\"ל", price_agorot=1000,
         emoji="🥤", is_vegan=True, sort_order=31),
    dict(name_he="בירה", name_en="Beer", category="drinks",
         description_he="בירה מהחבית", price_agorot=2600,
         emoji="🍺", is_vegan=True, sort_order=32),
    dict(name_he="קפה הפוך", name_en="Cappuccino", category="drinks",
         description_he="קפה הפוך חם", price_agorot=1300,
         emoji="☕", sort_order=33),
    # --- קינוחים ---
    dict(name_he="מלבי", name_en="Malabi", category="desserts",
         description_he="מלבי עם סירופ ורדים, פיסטוק וקוקוס",
         price_agorot=1800, emoji="🍮", is_vegan=True, sort_order=40),
    dict(name_he="בקלאווה", name_en="Baklava", category="desserts",
         description_he="בקלאווה פיסטוק", price_agorot=1600,
         emoji="🍯", sort_order=41),
]

REWARDS: list[dict] = [
    dict(name_he="פיתה חמה במתנה", description_he="פיתה טרייה מהטאבון",
         cost_coins=60, emoji="🫓", sort_order=1),
    dict(name_he="מנת חמוצים", description_he="חמוצים של הבית",
         cost_coins=90, emoji="🥒", sort_order=2),
    dict(name_he="לימונענע במתנה", description_he="לימונענע קרה",
         cost_coins=140, emoji="🍋", sort_order=3),
    dict(name_he="מלבי המשורר", description_he="הקינוח של הבית",
         cost_coins=180, emoji="🍮", sort_order=4),
    dict(name_he="חומוס המשורר במתנה", description_he="מנת החומוס של הבית, עלינו",
         cost_coins=420, emoji="🫛", sort_order=5),
    dict(name_he="ארוחת משורר לשניים",
         description_he="שני חומוסים, סלט, פיתות ושתייה",
         cost_coins=900, emoji="👑", sort_order=6),
]


async def seed_all(db: AsyncSession) -> None:
    """Idempotent: safe to run on every startup."""
    menu_count = (await db.execute(select(func.count(MenuItem.id)))).scalar() or 0
    if menu_count == 0:
        db.add_all(MenuItem(**row) for row in MENU)

    reward_count = (await db.execute(select(func.count(Reward.id)))).scalar() or 0
    if reward_count == 0:
        db.add_all(Reward(**row) for row in REWARDS)

    if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
        email = settings.bootstrap_admin_email.lower()
        existing = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                User(
                    email=email,
                    full_name="מנהל המועדון",
                    role=UserRole.admin,
                    password_hash=hash_password(settings.bootstrap_admin_password),
                )
            )
        elif existing.role is not UserRole.admin:
            existing.role = UserRole.admin
            existing.password_hash = hash_password(settings.bootstrap_admin_password)

    await db.commit()
