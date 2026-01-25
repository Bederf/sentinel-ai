"""Application settings and configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    app_name: str = "BMS Intelligence"
    app_version: str = "0.1.0"
    debug: bool = False

    # CORS settings
    cors_origins: list[str] = ["http://localhost:3002", "http://localhost:5173"]

    # Claude AI settings
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 4096

    # Demo mode for pre-seeded responses
    demo_mode: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
