"""Tests for the real-time build log parser."""

from __future__ import annotations

from pathlib import Path

from cruine.utils.log_parser import LogParser


def test_classify_critical() -> None:
    parser = LogParser()
    assert parser.evaluate("FAILED: /out/target/x") == "critical"
    assert parser.stats.critical == 1
    assert parser.failed_lines


def test_classify_warning() -> None:
    parser = LogParser()
    assert parser.evaluate("main.c: warning: unused variable") == "warning"
    assert parser.stats.warnings == 1


def test_classify_progress() -> None:
    parser = LogParser()
    assert parser.evaluate("[ 42%] building target") == "progress"
    assert parser.stats.progress == 1


def test_classify_info() -> None:
    parser = LogParser()
    assert parser.evaluate("plain informational line") == "info"
    assert parser.stats.info == 1


def test_is_fatal() -> None:
    assert LogParser.is_fatal("ninja: build stopped: subcommand failed")
    assert not LogParser.is_fatal("ninja: build started")


def test_has_errors() -> None:
    parser = LogParser()
    assert not parser.has_errors
    parser.evaluate("fatal error: something broke")
    assert parser.has_errors


def test_parse_file_streams(tmp_path: Path) -> None:
    log_file = tmp_path / "build.log"
    log_file.write_text("line1\nFAILED: x\n[ 10%] go\n", encoding="utf-8")
    parser = LogParser()
    parser.parse_file(log_file)
    assert parser.stats.info == 1
    assert parser.stats.critical == 1
    assert parser.stats.progress == 1
