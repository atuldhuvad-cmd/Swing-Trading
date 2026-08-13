from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

# Absolute path for the DB in the project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "swing_trading.db"

class Settings(BaseSettings):
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"
    
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
