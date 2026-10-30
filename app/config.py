from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Where the data comes from: "postgres", or "memory" (demo data, no database needed).
    data_source: str = "postgres"
    database_url: str = "postgresql+asyncpg://luwo:luwo@localhost:5433/luwo"

    llm_provider: str = "claude"  # "claude" or "fake"
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-5-5"

    jwt_secret: str = "dev-only-secret-change-me-before-deploying-0000"
    jwt_expire_minutes: int = 480


settings = Settings()
