from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gemini_api_key: str
    gemini_model: str = "gemini-3.5-flash-lite"
    database_url: str
    embed_model: str
    embed_dim: int = 768
    embed_texts_per_minute: int = 50
    stale_after_minutes: int = 10

    # Tracing is optional: without keys the app still works, just untraced.
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()