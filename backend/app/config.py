from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

# Absolute path for the DB in the project root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "swing_trading.db"

class Settings(BaseSettings):
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"
    # Browser origins allowed to call the API directly (the Vite dev server).
    # Override with a JSON list in CORS_ALLOWED_ORIGINS if Vite runs elsewhere.
    cors_allowed_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
