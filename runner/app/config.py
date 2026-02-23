"""RLM Runner configuration — pydantic-settings based."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runner configuration loaded from environment variables."""

    # Network
    host: str = "127.0.0.1"
    port: int = 8010

    # Filesystem paths
    cases_dir: str = "/var/lib/sentinel/cases"
    output_dir: str = "/var/lib/sentinel/rlm_out"
    log_dir: str = "/var/log/rlm-runner"

    # Inference
    model_base_url: str = "http://127.0.0.1:11434/v1"
    model_name: str = "phi3:mini"
    model_allowlist: list[str] = [
        "phi3:mini",
        "llama3.2:1b",
        "tinydolphin",
        "nomic-embed-text",
    ]

    # Budget limits
    max_runtime_seconds: int = 120
    max_recursion_depth: int = 6
    max_tokens_per_call: int = 1200
    temperature: float = 0.1

    # Environment
    environment: str = "development"

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


settings = Settings()
