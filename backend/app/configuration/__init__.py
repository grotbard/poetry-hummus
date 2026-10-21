"""Application configuration.

Import the singleton from here:

    from app.configuration import settings
    settings.database.url
"""

from .main import (
    AppEnv,
    DatabaseSettings,
    GoogleOAuthSettings,
    LoyaltySettings,
    SecuritySettings,
    Settings,
    get_settings,
    settings,
)

__all__ = [
    "AppEnv",
    "DatabaseSettings",
    "GoogleOAuthSettings",
    "LoyaltySettings",
    "SecuritySettings",
    "Settings",
    "get_settings",
    "settings",
]
