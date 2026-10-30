from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://luwo:luwo@localhost:5433/luwo"

    llm_provider: str = "claude"  # "claude" or "fake"
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-5-5"

    jwt_secret: str = "dev-only-change-me"
    jwt_expire_minutes: int = 480


settings = Settings()
