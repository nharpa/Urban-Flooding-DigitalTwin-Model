"""Configuration management for Urban Flooding Digital Twin.

This module provides centralized configuration management using Pydantic Settings.
It handles environment variables for database connections, API tokens, and
external service configurations with automatic .env file loading.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, ClassVar
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file.

    Attributes
    ----------
    APP_NAME : str
        Application name identifier.
    API_TOKEN : str, optional
        Bearer token for API authentication.
    MONGODB_URL : str
        MongoDB connection URL (default: localhost:27017).
    MONGODB_NAME : str, optional
        Name of the MongoDB database to use.
    MONGO_INITDB_ROOT_USERNAME : str, optional
        MongoDB root username for authentication.
    MONGO_INITDB_ROOT_PASSWORD : str, optional
        MongoDB root password for authentication.
    WEATHER_API_TOKEN : str, optional
        API token for external weather service access.
    WEATHER_API_URL : str, optional
        Base URL for external weather API.
    """
    APP_NAME: str = "flood-backend"
    API_TOKEN: Optional[str] = None
    MONGODB_URL: str = "localhost:27017"
    MONGODB_NAME: Optional[str] = None
    MONGO_INITDB_ROOT_USERNAME: Optional[str] = None
    MONGO_INITDB_ROOT_PASSWORD: Optional[str] = None
    WEATHER_API_TOKEN: Optional[str] = None
    WEATHER_API_URL: Optional[str] = None

    env_path: ClassVar[str] = os.path.join(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    print(f"Loading environment variables from: {env_path}")
    model_config = SettingsConfigDict(env_file=env_path, extra="ignore")


settings = Settings()
