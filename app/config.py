from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]

# also export .env into os.environ (PIPELINE_ENABLED, TELEGRAM_*, POSTER_SALT, ...);
# real environment variables (e.g. set in the Renode panel) take precedence
load_dotenv(ROOT / ".env", override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    admin_username: str
    admin_password: str
    secret_key: str
    database_url: str = ""
    mapbox_token: str = ""
    mapbox_style: str = "mapbox://styles/mapbox/light-v11"

    session_hours: int = 12
    cookie_secure: bool = False          # set true behind HTTPS
    data_path: Path = ROOT / "data/app/listings.parquet"
    quality_path: Path = ROOT / "data/app/quality.json"
    log_dir: Path = ROOT / "logs"
    login_max_attempts: int = 5
    login_window_sec: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()
