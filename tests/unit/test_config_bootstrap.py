"""Offline tests for configuration bootstrap and JSON failure policy."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

import config


@pytest.mark.offline
def test_missing_live_config_uses_safe_default_without_writing(tmp_path: Path) -> None:
    """A fresh clone can load a missing live file from an in-memory default."""
    live_path = tmp_path / "config" / "channel_settings.json"
    default = {"__schema_version": 2}
    assert config.load_json_file(live_path, default) == default
    assert not live_path.exists()
    assert list(tmp_path.rglob("*")) == []


@pytest.mark.offline
@pytest.mark.parametrize(
    "example_name",
    [
        "channel_settings.example.json",
        "calibration_settings.example.json",
        "config_settings.example.json",
        "hardware_map.example.json",
        "notification_settings.example.json",
        "user_settings.example.json",
    ],
)
def test_public_example_configs_are_valid_json(repository_root: Path, example_name: str) -> None:
    """All public bootstrap examples parse as JSON objects."""
    path = repository_root / "config" / example_name
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    assert isinstance(payload, dict)


@pytest.mark.offline
def test_malformed_json_emits_diagnostic_and_uses_safe_fallback(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """Malformed scientific configuration must not fail silently."""
    path = tmp_path / "malformed.json"
    path.write_text('{"offset_current": ', encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="config"):
        result = config.load_json_file(path, {"offset_current": 0.0})
    assert result == {"offset_current": 0.0}
    assert "Configuration JSON load failed" in caplog.text


@pytest.mark.offline
def test_missing_config_keys_receive_runtime_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing scheduler and relay keys are normalized to safe defaults."""
    monkeypatch.setattr(config, "_config_settings", {})
    scheduler = config.get_scheduler_runtime_settings()
    relay = config._merged_config_section("RELAY_CONFIG", {"SAFE_MODE": True, "PORT": "", "BAUDRATE": 19200})
    assert scheduler == {"mode": "flexible_catch_up", "max_allowed_delay_sec": 300}
    assert relay["SAFE_MODE"] is True
    assert relay["PORT"] == ""


@pytest.mark.offline
def test_config_tests_never_touch_repository_runtime_directories(
    repository_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Config writes can be redirected entirely to ``tmp_path``."""
    target = tmp_path / "config" / "runtime.json"
    monkeypatch.setattr(config, "BASE_CONFIG_DIR", tmp_path / "config")
    assert config.save_json_file(target, {"safe": True}) is True
    assert json.loads(target.read_text(encoding="utf-8")) == {"safe": True}
    assert not (repository_root / "config" / "runtime.json").exists()
