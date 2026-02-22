from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    base_url: str = Field(default="http://localhost:8000", alias="BASE_URL")
    session_secret: str = Field(alias="SESSION_SECRET")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    session_cookie_max_age: int = Field(default=60 * 60 * 24 * 7, alias="SESSION_COOKIE_MAX_AGE")
    session_cookie_domain: str | None = Field(default=None, alias="SESSION_COOKIE_DOMAIN")
    session_cookie_path: str = Field(default="/", alias="SESSION_COOKIE_PATH")
    webhook_secret: str = Field(alias="WEBHOOK_SECRET")

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")

    master_key: str = Field(alias="MASTER_KEY")

    default_provider: str = Field(default="openai", alias="DEFAULT_PROVIDER")
    default_model: str = Field(default="openai:gpt-4o-mini", alias="DEFAULT_MODEL")

settings = Settings()
