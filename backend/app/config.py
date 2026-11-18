from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    gemini_api_key: str
    gemini_model: str = "gemini-3.5-flash-lite"
    database_url: str
    embed_model: str
    embed_dim: int = 768
    embed_texts_per_minute: int = 50
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()