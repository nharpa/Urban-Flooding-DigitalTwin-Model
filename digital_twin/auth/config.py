from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, ClassVar
import os


class Settings(BaseSettings):
    APP_NAME: str = "flood-backend"
    API_TOKEN: Optional[str] = None
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_NAME: Optional[str] = None
    WEATHER_API_TOKEN: Optional[str] = None
    WEATHER_API_URL: Optional[str] = None

    env_path: ClassVar[str] = os.path.join(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    print(f"Loading environment variables from: {env_path}")
    model_config = SettingsConfigDict(env_file=env_path, extra="ignore")


settings = Settings()
