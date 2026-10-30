from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Only for local development. Starting with it in any other environment is refused.
DEV_JWT_SECRET = "dev-only-secret-change-me-before-deploying-0000"
MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"  # "dev" for local work; anything else must set a real JWT_SECRET

    # Where the data comes from: "postgres", or "memory" (demo data, no database needed).
    data_source: str = "postgres"
    database_url: str = "postgresql+asyncpg://luwo:luwo@localhost:5433/luwo"

    llm_provider: str = "claude"  # "claude" or "fake"
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-5-5"
    # Thinking mode sent to Claude. "disabled" keeps the tool loop simple and fast.
    # Some models reject "disabled" (e.g. Sonnet 5.5 wants "between_tools"); empty = omit.
    llm_thinking: str = "disabled"
    # The most time one chat request may take in total (all model calls together).
    agent_timeout_seconds: float = 90.0

    jwt_secret: str = DEV_JWT_SECRET
    jwt_expire_minutes: int = 480

    @model_validator(mode="after")
    def check_secret(self) -> "Settings":
        if len(self.jwt_secret) < MIN_SECRET_LENGTH:
            raise ValueError(f"JWT_SECRET must be at least {MIN_SECRET_LENGTH} characters long")
        if self.app_env != "dev" and self.jwt_secret == DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET is still the built-in development value; set a real secret in .env")
        return self


settings = Settings()
