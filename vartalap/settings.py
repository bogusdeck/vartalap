import os
import re
from pathlib import Path
from typing import List, Optional, Any, Dict
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env variables into environment if present
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path)


class CLIConfig(BaseModel):
    command: str = "antigravity -p {prompt}"
    timeout_seconds: int = 60


class OllamaCloudConfig(BaseModel):
    endpoint: str = "https://ollama.example/api"
    model: str = "llama3.1-cloud"
    api_key: Optional[str] = None


class APIConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    api_key: Optional[str] = None


class LLMConfig(BaseModel):
    backend: str = "cli"  # cli | ollama_cloud | api
    cli: CLIConfig = Field(default_factory=CLIConfig)
    ollama_cloud: OllamaCloudConfig = Field(default_factory=OllamaCloudConfig)
    api: APIConfig = Field(default_factory=APIConfig)


class RedditConfig(BaseModel):
    storage_state_path: str = "./storage_state.json"
    inbox_url: str = "https://chat.reddit.com"
    chat_url: str = "https://chat.reddit.com"
    headless: bool = False


class AgentConfig(BaseModel):
    mode: str = "fast_browser"  # fast_browser | direct_api | browser
    watchlist: List[str] = Field(default_factory=list)
    max_steps_per_conversation: int = 6
    max_messages_per_day: int = 20
    dry_run: bool = True


class SchedulerConfig(BaseModel):
    polling_interval_minutes: int = 10


class SecurityConfig(BaseModel):
    api_key: Optional[str] = None


class Settings(BaseModel):
    llm: LLMConfig = Field(default_factory=LLMConfig)
    reddit: RedditConfig = Field(default_factory=RedditConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)


_settings_instance: Optional[Settings] = None


def resolve_env_vars(raw_text: str) -> str:
    """Replace ${VAR_NAME} or ${VAR_NAME:default} with environment variables."""

    def replacer(match: re.Match) -> str:
        expr = match.group(1).strip()
        if ":" in expr:
            var_name, default_val = expr.split(":", 1)
        else:
            var_name, default_val = expr, ""
        return os.getenv(var_name, default_val)

    # Pattern matches ${VAR_NAME} or ${VAR_NAME:default}
    pattern = re.compile(r"\$\{([^}]+)\}")
    return pattern.sub(replacer, raw_text)


def load_settings(config_path: Optional[str] = None) -> Settings:
    """Load settings from config.yaml, resolving env vars."""
    global _settings_instance
    if config_path is None:
        config_path = os.getenv("CONFIG_PATH", str(Path(__file__).parent.parent / "config.yaml"))

    path = Path(config_path)
    if not path.exists():
        _settings_instance = Settings()
        return _settings_instance

    with open(path, "r", encoding="utf-8") as f:
        raw_content = f.read()

    resolved_content = resolve_env_vars(raw_content)
    parsed_yaml = yaml.safe_load(resolved_content) or {}
    _settings_instance = Settings(**parsed_yaml)
    return _settings_instance


def get_settings() -> Settings:
    """Return cached settings instance or load it if not initialized."""
    global _settings_instance
    if _settings_instance is None:
        return load_settings()
    return _settings_instance


def reload_settings(config_path: Optional[str] = None) -> Settings:
    """Force reload settings from file (useful for hot-reloading per tick)."""
    # Reload .env as well
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
    return load_settings(config_path)
