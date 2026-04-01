"""Compatibility alias exposing the real ``app`` package as ``backend.app``."""

from __future__ import annotations

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parents[2] / "app")]
