"""Optional multimodal check of selected evidence images, kept behind one adapter.

Core detection never depends on this. Implementations must:
- receive only a few selected evidence_raw JPEGs (never every frame) and only after Developer 2 agrees
  that footage may leave our infrastructure;
- return strict structured output, and on any error/timeout return None so callers use the deterministic path.

Enable with POTPATROL_VALIDATOR=gemini plus GEMINI_API_KEY (environment or a git-ignored .env file).
CLI check of one image: python -m potpatrol_vision.validators path/to/event-001-raw.jpg
"""
from __future__ import annotations

import json
import os
import sys
from typing import Protocol

from .schema import env

DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
DEFAULT_MAX_VALIDATIONS = 5
DEFAULT_TIMEOUT_S = 20.0

_PROMPT = """You are checking one frame from a vehicle-mounted phone camera that an automatic detector flagged as a {category}.
Decide only from what is visible in this image whether it shows a {category} in the road surface.
Common false alarms: curbs, parking stops, sidewalk edges, manhole or utility covers, patched or resurfaced asphalt, shadows, puddles, stains, painted markings, shallow cracks.
Return is_hazard, your confidence in [0,1], and a one-sentence rationale describing only visible features.
Do not estimate size, depth, lane, road ownership, severity or injury risk."""

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "is_hazard": {"type": "BOOLEAN"},
        "confidence": {"type": "NUMBER"},
        "rationale": {"type": "STRING"},
    },
    "required": ["is_hazard", "confidence", "rationale"],
}
_SCAN_PROMPT = """Inspect only the visible road surface in this single vehicle-camera frame. Find visible potholes or broken/rough road surface requiring human review. Do not report curbs, parking stops, manhole covers, painted markings, shadows, intact patches or unrelated objects. Return hazards as normalized [x1,y1,x2,y2] boxes (0 to 1) tightly enclosing visible road damage, with confidence in [0,1] and category pothole or road_damage (use road_damage for rough/broken surface that is not clearly a pothole). Return an empty list when unsure or no road damage is visible. Do not infer location, time, severity, depth or size."""
_SCAN_SCHEMA = {"type": "OBJECT", "properties": {"hazards": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {"bbox": {"type": "ARRAY", "items": {"type": "NUMBER"}},
                                      "confidence": {"type": "NUMBER"},
                                      "category": {"type": "STRING", "enum": ["pothole", "road_damage"]}},
    "required": ["bbox", "confidence", "category"]}}}, "required": ["hazards"]}


class CandidateValidator(Protocol):
    def validate(self, image_path: str, category: str) -> dict | None:
        """Return {"is_hazard": bool, "confidence": float, "rationale": str, "provider": str, "model": str} or None."""

    def describe(self) -> dict | None:
        """Provider/model info for the manifest, or None when disabled."""


class NullValidator:
    def validate(self, image_path: str, category: str) -> dict | None:
        return None

    def describe(self) -> dict | None:
        return None


class GeminiValidator:
    def __init__(self, api_key: str, model: str = DEFAULT_GEMINI_MODEL, timeout_s: float = DEFAULT_TIMEOUT_S):
        from google import genai
        from google.genai import types

        self._types = types
        self.model = model
        self._client = genai.Client(api_key=api_key,
                                    http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))

    def describe(self) -> dict:
        return {"provider": "gemini", "model": self.model}

    def scan(self, image_path: str) -> list[dict] | None:
        """An independent frame scan; None means failure, not a negative frame."""
        try:
            with open(image_path, "rb") as f:
                image = f.read()
            t = self._types
            resp = self._client.models.generate_content(
                model=self.model,
                contents=[t.Part.from_bytes(data=image, mime_type="image/jpeg"), _SCAN_PROMPT],
                config=t.GenerateContentConfig(temperature=0.0, response_mime_type="application/json",
                                               response_schema=_SCAN_SCHEMA,
                                               automatic_function_calling=t.AutomaticFunctionCallingConfig(disable=True)),
            )
            return json.loads(resp.text)["hazards"]
        except Exception as e:  # noqa: BLE001 - required caller treats None as job failure
            print(f"validator: Gemini frame scan failed ({type(e).__name__})", file=sys.stderr)
            return None

    def validate(self, image_path: str, category: str) -> dict | None:
        try:
            with open(image_path, "rb") as f:
                image = f.read()
            t = self._types
            resp = self._client.models.generate_content(
                model=self.model,
                contents=[t.Part.from_bytes(data=image, mime_type="image/jpeg"),
                          _PROMPT.format(category=category)],
                config=t.GenerateContentConfig(temperature=0.0, response_mime_type="application/json",
                                               response_schema=_RESPONSE_SCHEMA,
                                               automatic_function_calling=t.AutomaticFunctionCallingConfig(
                                                   disable=True)),
            )
            data = json.loads(resp.text)
            conf = float(data["confidence"])
            if not isinstance(data["is_hazard"], bool) or not 0.0 <= conf <= 1.0:
                return None
            return {"is_hazard": data["is_hazard"], "confidence": round(conf, 3),
                    "rationale": str(data["rationale"]).strip()[:300], **self.describe()}
        except Exception as e:  # noqa: BLE001 - optional layer: any failure falls back to the deterministic path
            print(f"validator: gemini check of {os.path.basename(image_path)} failed: {type(e).__name__}",
                  file=sys.stderr)
            return None


def get_required_validator() -> GeminiValidator:
    """Required mode never silently falls back or searches for a dotenv file."""
    from .schema import AnalysisError

    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise AnalysisError("Gemini required: GEMINI_API_KEY is not configured")
    try:
        return GeminiValidator(key, model=env("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
                               timeout_s=float(env("VALIDATE_TIMEOUT_S", str(DEFAULT_TIMEOUT_S))))
    except Exception as e:
        raise AnalysisError(f"Gemini required: SDK initialization failed ({type(e).__name__})") from e


def load_dotenv() -> None:
    """Load KEY=VALUE lines from the nearest .env (cwd upward, then the repo root) without overriding real env vars."""
    here = os.path.abspath(os.getcwd())
    candidates = []
    while True:
        candidates.append(os.path.join(here, ".env"))
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    candidates.append(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                   ".env"))
    path = next((p for p in candidates if os.path.isfile(p)), None)
    if not path:
        return
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def max_validations() -> int:
    try:
        limit = int(env("VALIDATE_MAX", str(DEFAULT_MAX_VALIDATIONS)))
        if limit < 0:
            raise ValueError("negative image limit")
        return limit
    except ValueError:
        print("validator: invalid POTPATROL_VALIDATE_MAX; skipping image checks", file=sys.stderr)
        return 0


def get_validator() -> CandidateValidator:
    """Gemini only when explicitly enabled and a key exists; otherwise the deterministic NullValidator."""
    setting = env("VALIDATOR").lower()
    if setting and setting != "gemini":
        return NullValidator()
    try:
        load_dotenv()
    except Exception as e:  # Optional configuration must not fail core detection.
        print(f"validator: configuration unavailable ({type(e).__name__}); skipping", file=sys.stderr)
        return NullValidator()
    if env("VALIDATOR").lower() != "gemini":
        return NullValidator()
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        print("validator: POTPATROL_VALIDATOR=gemini but GEMINI_API_KEY is not set; skipping", file=sys.stderr)
        return NullValidator()
    try:
        return GeminiValidator(key, model=env("GEMINI_MODEL", DEFAULT_GEMINI_MODEL),
                               timeout_s=float(env("VALIDATE_TIMEOUT_S", str(DEFAULT_TIMEOUT_S))))
    except Exception as e:  # noqa: BLE001 - e.g. google-genai not installed
        print(f"validator: gemini unavailable ({type(e).__name__}: {e}); skipping", file=sys.stderr)
        return NullValidator()


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Check one evidence JPEG with Gemini")
    ap.add_argument("image_path")
    ap.add_argument("--category", default="pothole")
    a = ap.parse_args(argv)
    load_dotenv()
    os.environ.setdefault("POTPATROL_VALIDATOR", "gemini")
    v = get_validator()
    if isinstance(v, NullValidator):
        return 1
    result = v.validate(a.image_path, a.category)
    print(json.dumps(result, indent=2))
    return 0 if result is not None else 1


if __name__ == "__main__":
    sys.exit(main())
