"""Application configuration.

Import the singleton from here:

    from app.configuration import settings
    settings.database.url
"""

from .main import (
    AppEnv,
    ConfigurationError,
    DatabaseSettings,
    GoogleOAuthSettings,
    LoyaltySettings,
    MenuSettings,
    SecuritySettings,
    Settings,
    get_settings,
    settings,
)

__all__ = [
    "AppEnv",
    "ConfigurationError",
    "DatabaseSettings",
    "GoogleOAuthSettings",
    "LoyaltySettings",
    "MenuSettings",
    "SecuritySettings",
    "Settings",
    "get_settings",
    "settings",
]
