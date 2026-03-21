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
            "heavy": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
            "medium": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
            "light": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
            "chat_ai": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001"},
            "chat_tech": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
        },
    },
    "cloud_dev": {
        "mode": "cloud",
        "routing": {
            "heavy": {"provider": "ollama_cloud", "model": "minimax-m2.7:cloud"},
            "medium": {"provider": "ollama_cloud", "model": "minimax-m2.7:cloud"},
            "light": {"provider": "ollama_cloud", "model": "minimax-m2.7:cloud"},
            "chat_ai": {"provider": "ollama_cloud", "model": "minimax-m2.7:cloud"},
            "chat_tech": {"provider": "ollama_cloud", "model": "minimax-m2.7:cloud"},
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
