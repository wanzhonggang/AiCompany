import json
import os
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "llm_config.json"
ENV_FILE = BASE_DIR / ".env"


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


def _read_env_file() -> dict[str, str]:
    """Read simple KEY=VALUE pairs from backend/.env without mutating os.environ."""
    if not ENV_FILE.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_env_value(name: str) -> str:
    """Return an environment variable, falling back to backend/.env."""
    return os.getenv(name, _read_env_file().get(name, ""))


def load_llm_config() -> dict:
    """Load LLM provider configuration from JSON file (always reads fresh)."""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_provider(name: str | None = None) -> dict | None:
    """Get a specific provider config, or the default if name is None."""
    config = load_llm_config()
    if not name:
        name = config.get("default_provider", "")
    for p in config.get("providers", []):
        if p["name"] == name:
            provider = dict(p)
            env_key = provider.get("api_key_env") or f"{provider['name'].upper()}_API_KEY"
            env_api_key = get_env_value(env_key)
            if env_api_key:
                provider["api_key"] = env_api_key
            return provider
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
