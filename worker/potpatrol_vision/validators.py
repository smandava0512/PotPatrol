"""Optional multimodal layer (e.g. Snowflake Cortex), kept behind one adapter.

Core detection never depends on this. Implementations must:
- receive only a few selected evidence_raw JPEGs (never every frame) and only after Developer 2 agrees
  that footage may leave our infrastructure;
- return strict structured output, and on any error/timeout return None so callers use the deterministic path.
"""
from __future__ import annotations

from typing import Protocol


class CandidateValidator(Protocol):
    def validate(self, image_path: str, category: str) -> dict | None:
        """Return {"is_hazard": bool, "confidence": float, "rationale": str, "provider": str} or None."""


class NullValidator:
    def validate(self, image_path: str, category: str) -> dict | None:
        return None


def get_validator() -> CandidateValidator:
    # A provider (e.g. Snowflake Cortex) is plugged in here only after its current image API, model and
    # limits are verified and credentials exist. Until then everything uses the deterministic path.
    return NullValidator()
