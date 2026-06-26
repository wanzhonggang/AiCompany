import json
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "llm_config.json"
ENV_FILE = BASE_DIR / ".env"
LOCAL_ENV_FILE = BASE_DIR / ".env.local"

# Load environment variables
load_dotenv(dotenv_path=ENV_FILE)
load_dotenv(dotenv_path=LOCAL_ENV_FILE, override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE))

    secret_key: str = "change-me-in-production"
    encryption_key: str | None = None
    encryption_passphrase: str = "default-change-me-in-production"
    encryption_salt: str = "default-salt-change-me"
    database_url: str | None = None

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        db_path = DATA_DIR / "ai_employees.db"
        return f"sqlite+aiosqlite:///{db_path}"


settings = Settings()


def _read_env_file() -> dict[str, str]:
    """Read simple KEY=VALUE pairs from backend env files without mutating os.environ."""
    files = [ENV_FILE, LOCAL_ENV_FILE]

    values: dict[str, str] = {}
    for env_file in files:
        if not env_file.exists():
            continue
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
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


def save_llm_config(config: dict) -> None:
    CONFIG_FILE.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def set_env_value(name: str, value: str) -> None:
    """Persist a secret into backend/.env.local without exposing it in JSON config."""
    values = _read_env_file()
    values[name] = value
    LOCAL_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={val}" for key, val in sorted(values.items())]
    LOCAL_ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def get_provider_config(name: str | None = None) -> dict | None:
    """Get provider config without attaching any global API key."""
    config = load_llm_config()
    if not name:
        name = config.get("default_provider", "")
    for p in config.get("providers", []):
        if p["name"] == name:
            return dict(p)
    return None


def get_default_model() -> str:
    return load_llm_config().get("default_model", "deepseek-chat")


def get_providers_safe(configured_names: set[str] | None = None) -> list[dict]:
    """Return provider list with API keys stripped for frontend display."""
    config = load_llm_config()
    safe = []
    for p in config.get("providers", []):
        env_key = p.get("api_key_env") or f"{p['name'].upper()}_API_KEY"
        has_key = p["name"] in configured_names if configured_names is not None else bool(get_env_value(env_key))
        safe.append({
            "name": p["name"],
            "display_name": p["display_name"],
            "base_url": p.get("base_url", ""),
            "api_key_env": env_key,
            "protocol": p.get("protocol", "openai_compatible"),
            "status": p.get("status", "ready"),
            "configured": has_key,
            "last_refreshed_at": p.get("last_refreshed_at"),
            "models": p.get("models", []),
        })
    return safe
