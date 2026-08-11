"""Tests for the configurable status logger."""

from __future__ import annotations

import io
import re

from cruine.utils.logger import (
    DEFAULT_FORMAT,
    STATUSES,
    Logger,
    LogLevel,
    color_code,
)

NO_COLOR = "NO_COLOR"


def _logger(**kwargs) -> Logger:
    return Logger(stream=io.StringIO(), no_color=True, **kwargs)


def test_status_registry_is_large() -> None:
    assert len(STATUSES) >= 50


def test_statuses_start_uppercase_not_allcaps() -> None:
    for name in STATUSES:
        assert name[0].isupper(), name
        assert not name.isupper(), name


def test_default_format_24h_bracketed_status(capsys) -> None:
    log = _logger()
    log.info("hello")
    line = log.stream.getvalue().strip()
    assert re.fullmatch(r"\[\d{2}:\d{2}:\d{2}\] \[Info\] hello", line)


def test_status_label_is_bracketed() -> None:
    log = _logger()
    log.build("kernel")
    assert "[Build]" in log.stream.getvalue()


def test_dynamic_status_method() -> None:
    log = _logger()
    log.fetch("sources")
    assert "[Fetch]" in log.stream.getvalue()


def test_status_lookup_is_case_insensitive() -> None:
    log = _logger()
    log.emit("BUILD", "x")
    assert "[Build]" in log.stream.getvalue()


def test_arbitrary_format_with_variables() -> None:
    log = _logger(fmt="{level} | {status}: {msg}")
    log.merge("a and b")
    assert log.stream.getvalue().strip() == "INFO | Merge: a and b"


def test_any_format_accepted() -> None:
    log = _logger(fmt=">>> {status} {message} <<<")
    log.warning("careful")
    assert log.stream.getvalue().strip() == ">>> Warn careful <<<"


def test_empty_format_prints_message_only() -> None:
    log = _logger(fmt="")
    log.info("bare")
    assert log.stream.getvalue().strip() == "bare"


def test_unknown_placeholder_renders_empty() -> None:
    log = _logger(fmt="{nope} {message}")
    log.info("safe")
    assert log.stream.getvalue().strip() == "safe"


def test_custom_timestamp_format() -> None:
    log = _logger(timestamp_format="%Y")
    log.info("y")
    assert re.fullmatch(r"\[20\d\d\] \[Info\] y", log.stream.getvalue().strip())


def test_colors_only_when_enabled() -> None:
    log = Logger(stream=io.StringIO(), no_color=False, fmt=DEFAULT_FORMAT)
    log.info("colored")
    line = log.stream.getvalue()
    assert "\x1b[" in line
    log_no = Logger(stream=io.StringIO(), no_color=True)
    log_no.info("plain")
    assert "\x1b[" not in log_no.stream.getvalue()


def test_debug_hidden_without_verbose() -> None:
    log = _logger()
    log.debug("secret")
    assert log.stream.getvalue() == ""


def test_debug_shown_with_verbose() -> None:
    log = _logger(verbose=True)
    log.debug("seen")
    assert "[Debug]" in log.stream.getvalue()


def test_level_threshold() -> None:
    log = _logger()
    log.emit("Trace", "t")
    assert log.stream.getvalue() == ""


def test_config_override_label_and_color() -> None:
    log = _logger()
    log.apply({"log": {"statuses": {"Build": {"label": "BUILDING", "color": "bright_blue"}}}})
    log.build("kernel")
    assert "[BUILDING]" in log.stream.getvalue()


def test_config_override_verbose() -> None:
    log = _logger()
    log.apply({"log": {"verbose": True}})
    log.debug("shown")
    assert "[Debug]" in log.stream.getvalue()


def test_color_code_names() -> None:
    assert color_code("bright red") == "\033[91m"
    assert color_code("bold") == "\033[1m"
    assert color_code("bogus") == ""
    assert "\x1b" in color_code("\x1b[35m")


def test_message_with_braces_survives_formatting() -> None:
    log = _logger(fmt="{ts} {status} {message}")
    log.info("size {n} bytes")
    assert "{n}" in log.stream.getvalue()


def test_unknown_status_uses_capitalised_name() -> None:
    log = _logger()
    log.emit("Zzz", "m")
    assert "[Zzz]" in log.stream.getvalue()


def test_raw_methods_still_work() -> None:
    log = _logger()
    log.raw("a")
    log.raw_error("b")
    log.raw_warn("c")
    log.raw_dim("d")
    assert log.stream.getvalue().splitlines() == ["a", "b", "c", "d"]


def test_level_enum_members() -> None:
    assert LogLevel.DEBUG < LogLevel.INFO < LogLevel.SUCCESS < LogLevel.ERROR
