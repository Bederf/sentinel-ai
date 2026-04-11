"""
SENTINEL Model Routing Profiles (Phase 163).

Three profiles cover the three deployment contexts:
  api_prod  — production cloud via direct Anthropic API
  cloud_dev — development via Ollama cloud abstraction layer
  local_full — air-gapped SBC with local Ollama only

Model strings must match what settings.py currently uses.
Update here when upgrading models.
"""

from typing import Any

# Task classes — valid values for model_gateway.call(task_class=...)
VALID_TASK_CLASSES = frozenset({"heavy", "medium", "light", "chat_ai", "chat_tech"})

ROUTING_PROFILES: dict[str, dict[str, Any]] = {
    "api_prod": {
        "mode": "api",
        "routing": {
            "heavy": {"provider": "minimax", "model": "MiniMax-M2.7"},
            "medium": {"provider": "minimax", "model": "MiniMax-M2.7"},
            "light": {"provider": "minimax", "model": "MiniMax-M2.7"},
            "chat_ai": {"provider": "minimax", "model": "MiniMax-M2.7"},
            "chat_tech": {"provider": "minimax", "model": "MiniMax-M2.7"},
        },
    },
    "cloud_dev": {
        "mode": "api",
        "routing": {
            "heavy": {"provider": "minimax", "model": "MiniMax-M2.7"},
            "medium": {"provider": "minimax", "model": "MiniMax-M2.7"},
            "light": {"provider": "minimax", "model": "MiniMax-M2.7"},
            "chat_ai": {"provider": "minimax", "model": "MiniMax-M2.7"},
            "chat_tech": {"provider": "minimax", "model": "MiniMax-M2.7"},
        },
    },
    "local_full": {
        "mode": "local",
        "routing": {
            "heavy": {"provider": "ollama", "model": "deepseek-r1:14b"},
            "medium": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
            "light": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
            "chat_ai": {"provider": "ollama", "model": "qwen2.5:7b-instruct"},
            "chat_tech": {"provider": "ollama", "model": "deepseek-r1:14b"},
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
