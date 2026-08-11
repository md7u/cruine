"""Tests for the Cruine user configuration (config.toml)."""

from __future__ import annotations

import io

from cruine.config.settings import (
    DEFAULT_SETTINGS,
    config_path,
    format_config,
    load_settings,
    write_template,
)
from cruine.utils.logger import configure_logger, log


def _write(tmp_path, body: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_defaults_when_config_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CRUINE_CONFIG", str(tmp_path / "missing.toml"))
    settings = load_settings()
    assert settings["log"]["format"].startswith("[{ts}]")
    assert settings["log"]["timestamp_format"] == "%H:%M:%S"
    assert settings["general"]["program"] == "cru"


def test_merge_overrides_and_keeps_defaults(monkeypatch, tmp_path) -> None:
    path = _write(tmp_path, '[log]\nformat = "{level} {message}"\n')
    monkeypatch.setenv("CRUINE_CONFIG", str(path))
    settings = load_settings()
    assert settings["log"]["format"] == "{level} {message}"
    assert settings["log"]["timestamp_format"] == "%H:%M:%S"


def test_statuses_override_loaded(monkeypatch, tmp_path) -> None:
    path = _write(tmp_path, '[log.statuses]\nBuild = { label = "B", color = "red" }\n')
    monkeypatch.setenv("CRUINE_CONFIG", str(path))
    settings = load_settings()
    assert settings["log"]["statuses"]["Build"] == {"label": "B", "color": "red"}


def test_invalid_toml_falls_back_to_defaults(monkeypatch, tmp_path) -> None:
    path = _write(tmp_path, "[log\nthis is not toml ]")
    monkeypatch.setenv("CRUINE_CONFIG", str(path))
    assert load_settings() == DEFAULT_SETTINGS


def test_config_path_env_override(monkeypatch, tmp_path) -> None:
    target = tmp_path / "x" / "config.toml"
    monkeypatch.setenv("CRUINE_CONFIG", str(target))
    assert config_path() == target


def test_write_template(monkeypatch, tmp_path) -> None:
    target = tmp_path / "config.toml"
    monkeypatch.setenv("CRUINE_CONFIG", str(target))
    written = write_template()
    assert written == target
    text = target.read_text(encoding="utf-8")
    assert "[{ts}]" in text
    assert "[log.statuses]" in text


def test_write_template_refuses_overwrite(monkeypatch, tmp_path) -> None:
    target = _write(tmp_path, "[general]\n")
    monkeypatch.setenv("CRUINE_CONFIG", str(target))
    try:
        write_template()
        raise AssertionError("expected FileExistsError")
    except FileExistsError:
        pass


def test_format_config_reports(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CRUINE_CONFIG", str(tmp_path / "none.toml"))
    text = format_config(load_settings())
    assert "log.format" in text
    assert "program" in text


def test_configure_logger_applies_config(monkeypatch, tmp_path) -> None:
    path = _write(tmp_path, '[log]\nformat = "[{status}] {message}"\n')
    monkeypatch.setenv("CRUINE_CONFIG", str(path))
    stream = io.StringIO()
    monkeypatch.setattr(log, "stream", stream)
    monkeypatch.setattr(log, "no_color", True)
    configure_logger()
    log.info("hi")
    assert stream.getvalue().strip() == "[Info] hi"


def test_configure_logger_cli_overrides_config(monkeypatch, tmp_path) -> None:
    path = _write(tmp_path, "[log]\nverbose = true\n")
    monkeypatch.setenv("CRUINE_CONFIG", str(path))
    stream = io.StringIO()
    monkeypatch.setattr(log, "stream", stream)
    monkeypatch.setattr(log, "no_color", True)
    configure_logger(verbose=False)
    log.debug("hidden")
    assert stream.getvalue() == ""
