"""
SENTINEL Model Routing Profiles (Phase 183 - Fallback Support).

Three profiles cover the three deployment contexts:
  api_prod  — production cloud with provider fallback chains
  cloud_dev — development via API with fallback chains
  local_full — air-gapped SBC with local Ollama only (no fallback to cloud)

Each routing entry is now an ordered list of [provider, model] pairs for fallback.
The gateway tries each in sequence until one succeeds.

For local_full: fallback_enabled=false enforces strict local-only operation.
For api_prod/cloud_dev: fallback_enabled=true enables cascading fallback.

Model strings must match what settings.py currently uses.
Update here when upgrading models.
"""

from typing import Any

# Task classes — valid values for model_gateway.call(task_class=...)
VALID_TASK_CLASSES = frozenset({"heavy", "medium", "light", "chat_ai", "chat_tech"})

ROUTING_PROFILES: dict[str, dict[str, Any]] = {
    "api_prod": {
        "mode": "api",
        "fallback_enabled": True,
        "routing": {
            "heavy": [
                {"provider": "minimax", "model": "MiniMax-M2.7"},
                {"provider": "anthropic", "model": "claude-opus-4-6"},
            ],
            "medium": [
                {"provider": "minimax", "model": "MiniMax-M2.7"},
                {"provider": "anthropic", "model": "claude-sonnet-4-6"},
            ],
            "light": [
                {"provider": "minimax", "model": "MiniMax-M2.7"},
                {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
            ],
            "chat_ai": [
                {"provider": "minimax", "model": "MiniMax-M2.7"},
                {"provider": "anthropic", "model": "claude-opus-4-6"},
            ],
            "chat_tech": [
                {"provider": "minimax", "model": "MiniMax-M2.7"},
                {"provider": "anthropic", "model": "claude-opus-4-6"},
            ],
        },
    },
    "cloud_dev": {
        "mode": "api",
        "fallback_enabled": True,
        "routing": {
            "heavy": [
                {"provider": "minimax", "model": "MiniMax-M2.7"},
                {"provider": "anthropic", "model": "claude-opus-4-6"},
            ],
            "medium": [
                {"provider": "minimax", "model": "MiniMax-M2.7"},
                {"provider": "anthropic", "model": "claude-sonnet-4-6"},
            ],
            "light": [
                {"provider": "minimax", "model": "MiniMax-M2.7"},
                {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
            ],
            "chat_ai": [
                {"provider": "minimax", "model": "MiniMax-M2.7"},
                {"provider": "anthropic", "model": "claude-opus-4-6"},
            ],
            "chat_tech": [
                {"provider": "minimax", "model": "MiniMax-M2.7"},
                {"provider": "anthropic", "model": "claude-opus-4-6"},
            ],
        },
    },
    "local_full": {
        "mode": "local",
        "fallback_enabled": False,  # Strict: no fallback to cloud/api
        "routing": {
            "heavy": [
                {"provider": "ollama", "model": "deepseek-r1:14b"},
            ],
            "medium": [
                {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
            ],
            "light": [
                {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
            ],
            "chat_ai": [
                {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
            ],
            "chat_tech": [
                {"provider": "ollama", "model": "deepseek-r1:14b"},
            ],
        },
    },
}


def get_profile(profile_name: str) -> dict[str, Any]:
    """
    Return the routing profile dict for the given name.
    Raises ValueError for unknown profiles.
    """
    if profile_name not in ROUTING_PROFILES:
        valid = ", ".join(sorted(ROUTING_PROFILES.keys()))
        raise ValueError(f"Unknown routing profile '{profile_name}'. Valid profiles: {valid}")
    return ROUTING_PROFILES[profile_name]
