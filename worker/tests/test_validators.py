"""Offline checks: optional validation must never break detection or widen sharing."""
import pytest

from potpatrol_vision import validators


@pytest.mark.parametrize("setting", ["off", None, "gemini"])
@pytest.mark.parametrize("error", [PermissionError, UnicodeError])
def test_unavailable_dotenv_does_not_break_optional_validation(monkeypatch, setting, error):
    monkeypatch.delenv("POTPATROL_VALIDATOR", raising=False)
    monkeypatch.delenv("ROADWATCH_VALIDATOR", raising=False)
    if setting is not None:
        monkeypatch.setenv("POTPATROL_VALIDATOR", setting)
    calls = []

    def unreadable():
        calls.append(1)
        raise error("synthetic configuration failure")

    monkeypatch.setattr(validators, "load_dotenv", unreadable)
    assert isinstance(validators.get_validator(), validators.NullValidator)
    if setting == "off":
        assert calls == []


@pytest.mark.parametrize("limit", ["bad", "-1", "1.5", "0"])
def test_invalid_or_zero_image_limit_sends_nothing(monkeypatch, limit):
    from potpatrol_vision.pipeline import _validate_events

    monkeypatch.setenv("POTPATROL_VALIDATE_MAX", limit)
    events = [{"confidence": 0.9, "category": "pothole", "evidence_raw_path": "not-read.jpg"}
              for _ in range(25)]
    calls = []

    class Validator:
        def validate(self, path, category):
            calls.append(path)

    _validate_events(events, ".", Validator())
    assert calls == []


@pytest.mark.parametrize("limit, expected", [("2", 2), ("5", 5)])
def test_valid_image_limit_is_respected(monkeypatch, limit, expected):
    monkeypatch.setenv("POTPATROL_VALIDATE_MAX", limit)
    assert validators.max_validations() == expected
