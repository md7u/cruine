"""Real-time build error filtering engine."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from cruine.utils.logger import Logger

_FAILURE_PATTERNS = (
    re.compile(r"\bFAILED:"),
    re.compile(r"\bfatal error:"),
    re.compile(r"\bninja: build stopped: subcommand failed"),
    re.compile(r"\bmake: \*\*\*"),
    re.compile(r"\berror:\s"),
    re.compile(r"\bError:\s"),
    re.compile(r"\bno space left on device\b", re.IGNORECASE),
    re.compile(r"\bout of memory\b", re.IGNORECASE),
    re.compile(r"\bKilled\b"),
    re.compile(r"\bSegmentation fault\b"),
)

_WARNING_PATTERNS = (
    re.compile(r"\bwarning:\s", re.IGNORECASE),
    re.compile(r"\bWARNING\b"),
    re.compile(r"\bNOTE:\b"),
)

_PROGRESS_PATTERN = re.compile(r"\[\s*\d{1,3}%\]")


@dataclass
class LogStats:
    critical: int = 0
    warnings: int = 0
    progress: int = 0
    info: int = 0


class LogParser:
    """Classifies build log lines in real time using regex patterns."""

    def __init__(self, logger: Logger | None = None) -> None:
        self.logger = logger
        self.stats = LogStats()
        self.failed_lines: list[str] = []

    def evaluate(self, line: str) -> str:
        """Classify a single line; returns its category name."""
        stripped = line.rstrip("\n")
        if any(pattern.search(stripped) for pattern in _FAILURE_PATTERNS):
            self.stats.critical += 1
            self.failed_lines.append(stripped)
            self._emit(stripped, "error")
            return "critical"
        if _PROGRESS_PATTERN.search(stripped):
            self.stats.progress += 1
            self._emit(stripped, "dim")
            return "progress"
        if any(pattern.search(stripped) for pattern in _WARNING_PATTERNS):
            self.stats.warnings += 1
            self._emit(stripped, "warn")
            return "warning"
        self.stats.info += 1
        self._emit(stripped)
        return "info"

    @staticmethod
    def is_fatal(line: str) -> bool:
        return bool(re.search(r"ninja: build stopped: subcommand failed", line, re.IGNORECASE))

    @property
    def has_errors(self) -> bool:
        return self.stats.critical > 0

    def summary(self) -> None:
        if self.logger is None:
            return
        stats = self.stats
        self.logger.info(
            f"Log stats: {stats.critical} error line(s), {stats.warnings} warning line(s), "
            f"{stats.progress} progress line(s), {stats.info} info line(s)"
        )

    def parse_file(self, path: Path) -> None:
        with Path(path).open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                self.evaluate(line.rstrip("\n"))
        self.summary()

    def _emit(self, line: str, kind: str | None = None) -> None:
        if self.logger is None:
            return
        if kind == "error":
            self.logger.raw_error(line)
        elif kind == "warn":
            self.logger.raw_warn(line)
        elif kind == "dim":
            self.logger.raw_dim(line)
        else:
            self.logger.raw(line)
