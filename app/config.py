from pydantic import Field, model_validator
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

    # Connections kept open to PostgreSQL, plus extra ones allowed during a burst. Raise them if the load
    # test shows requests waiting for a free connection (the README records the values used in the measurements).
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)

    llm_provider: str = "claude"  # "claude" or "fake"
    # With LLM_PROVIDER=fake: seconds the scripted model waits before answering (imitates model latency in load tests)
    fake_llm_delay: float = Field(default=0.0, ge=0)
    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-5-5"
    # Thinking mode sent to Claude. "disabled" keeps the tool loop simple and fast.
    # Some models reject "disabled" (e.g. Sonnet 5.5 wants "between_tools"); empty = omit.
    llm_thinking: str = "disabled"
    # The most time one chat request may take in total (all model calls together).
    agent_timeout_seconds: float = 90.0

    # Web pages allowed to call the API from a browser (the Expo web preview). Native apps don't need CORS.
    cors_origins: str = "http://localhost:8081,http://localhost:19006"

    log_level: str = "INFO"
    log_json: bool = True  # one JSON object per line; False gives readable colored lines for local work
    # Record what users typed (and tool arguments) in the logs. The task asks for the user request in the
    # logs, so this is ON in development; anywhere else it is OFF unless you set LOG_USER_TEXT=true,
    # because messages may contain personal data (names of children) that you may not be allowed to store.
    log_user_text: bool | None = None  # None = decided by APP_ENV, see check_secret
    # If set, /metrics requires "Authorization: Bearer <token>". Empty = open (fine for local use).
    metrics_token: str = ""

    jwt_secret: str = DEV_JWT_SECRET
    jwt_expire_minutes: int = 480

    @model_validator(mode="after")
    def check_secret(self) -> "Settings":
        if self.log_user_text is None:
            self.log_user_text = self.app_env == "dev"
        if len(self.jwt_secret) < MIN_SECRET_LENGTH:
            raise ValueError(f"JWT_SECRET must be at least {MIN_SECRET_LENGTH} characters long")
        if self.app_env != "dev" and self.jwt_secret == DEV_JWT_SECRET:
            raise ValueError("JWT_SECRET is still the built-in development value; set a real secret in .env")
        return self


settings = Settings()
