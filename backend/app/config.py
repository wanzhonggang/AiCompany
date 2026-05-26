import json
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "llm_config.json"


class Settings(BaseSettings):
    secret_key: str = "change-me-in-production"

    @property
    def database_url(self) -> str:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        db_path = DATA_DIR / "ai_employees.db"
        return f"sqlite+aiosqlite:///{db_path}"

    class Config:
        env_file = ".env"


settings = Settings()


@lru_cache()
def load_llm_config() -> dict:
    """Load LLM provider configuration from JSON file."""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_provider(name: str | None = None) -> dict | None:
    """Get a specific provider config, or the default if name is None."""
    config = load_llm_config()
    if not name:
        name = config.get("default_provider", "")
    for p in config.get("providers", []):
        if p["name"] == name:
            return p
    return None


def get_default_model() -> str:
    return load_llm_config().get("default_model", "deepseek-chat")


def get_providers_safe() -> list[dict]:
    """Return provider list with API keys stripped for frontend display."""
    config = load_llm_config()
    safe = []
    for p in config.get("providers", []):
        safe.append({
            "name": p["name"],
            "display_name": p["display_name"],
            "models": p.get("models", []),
        })
    return safe
