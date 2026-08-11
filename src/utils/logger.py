"""Terminal logger with a rich, fully configurable status system.

The default line format is ``[HH:MM:SS] [Status] message`` (24-hour clock,
status capitalised). The format string, timestamp, per-status labels and
colours are all configurable from ``~/.config/cruine/config.toml``.

Format strings accept any combination of variable placeholders, e.g.::

    "[{ts}] [{status}] {message}"
    "{level} | {message}"
    ""                                  (message only)

Variables: ``ts``, ``time``, ``date``, ``status``, ``label``, ``level``,
``message``, ``msg``, ``program``, ``pid``, ``hostname``, ``counter``,
``elapsed``, ``color``, ``reset``, ``bold``, ``dim``.
"""

from __future__ import annotations

import os
import platform
import sys
import time
from dataclasses import dataclass, replace
from enum import IntEnum
from typing import TextIO

DEFAULT_FORMAT = "[{ts}] [{color}{status}{reset}] {message}"
DEFAULT_TIMESTAMP_FORMAT = "%H:%M:%S"


class LogLevel(IntEnum):
    TRACE = 5
    DEBUG = 10
    INFO = 20
    SUCCESS = 25
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


class _Style:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"


_COLOR_NAMES = {
    "black": _Style.BLACK,
    "red": _Style.RED,
    "green": _Style.GREEN,
    "yellow": _Style.YELLOW,
    "blue": _Style.BLUE,
    "magenta": _Style.MAGENTA,
    "cyan": _Style.CYAN,
    "white": _Style.WHITE,
    "gray": _Style.GRAY,
    "grey": _Style.GRAY,
    "bright_red": _Style.BRIGHT_RED,
    "bright_green": _Style.BRIGHT_GREEN,
    "bright_yellow": _Style.BRIGHT_YELLOW,
    "bright_blue": _Style.BRIGHT_BLUE,
    "bright_magenta": _Style.BRIGHT_MAGENTA,
    "bright_cyan": _Style.BRIGHT_CYAN,
    "bright_white": _Style.BRIGHT_WHITE,
    "bold": _Style.BOLD,
    "dim": _Style.DIM,
    "underline": _Style.UNDERLINE,
}


def color_code(value: object) -> str:
    """Resolve a colour name (``cyan``, ``bright red``, ``bold``) to ANSI."""
    text = str(value).strip()
    if "\x1b" in text:
        return text
    key = text.lower().replace(" ", "_")
    return _COLOR_NAMES.get(key, "")


@dataclass(frozen=True)
class Status:
    """A named log status with a severity level, colour and display label."""

    name: str
    level: LogLevel = LogLevel.INFO
    color: str = _Style.CYAN
    label: str = ""


def _status(
    name: str,
    level: LogLevel = LogLevel.INFO,
    color: str = _Style.CYAN,
) -> Status:
    return Status(name=name, level=level, color=color, label=name)


_INFO = LogLevel.INFO
_OK = LogLevel.SUCCESS
_WARN = LogLevel.WARNING
_ERR = LogLevel.ERROR
_FATAL = LogLevel.CRITICAL

_STATUS_DEFS: tuple[tuple[str, LogLevel, str], ...] = (
    ("Trace", LogLevel.TRACE, _Style.GRAY),
    ("Debug", LogLevel.DEBUG, _Style.GRAY),
    ("Info", _INFO, _Style.CYAN),
    ("Note", _INFO, _Style.GRAY),
    ("Detail", _INFO, _Style.GRAY),
    ("Notice", _INFO, _Style.GRAY),
    ("Event", _INFO, _Style.GRAY),
    ("Status", _INFO, _Style.CYAN),
    ("Result", _INFO, _Style.CYAN),
    ("Summary", _INFO, _Style.CYAN),
    ("Count", _INFO, _Style.CYAN),
    ("Ok", _OK, _Style.GREEN),
    ("Success", _OK, _Style.GREEN),
    ("Done", _OK, _Style.GREEN),
    ("Pass", _OK, _Style.GREEN),
    ("Passed", _OK, _Style.GREEN),
    ("Good", _OK, _Style.GREEN),
    ("Warn", _WARN, _Style.YELLOW),
    ("Warning", _WARN, _Style.YELLOW),
    ("Caution", _WARN, _Style.YELLOW),
    ("Error", _ERR, _Style.RED),
    ("Fail", _ERR, _Style.RED),
    ("Failed", _ERR, _Style.RED),
    ("Critical", _FATAL, _Style.MAGENTA),
    ("Fatal", _FATAL, _Style.MAGENTA),
    ("Panic", _FATAL, _Style.MAGENTA),
    ("Abort", _FATAL, _Style.MAGENTA),
    ("Start", _INFO, _Style.CYAN),
    ("Begin", _INFO, _Style.CYAN),
    ("Init", _INFO, _Style.CYAN),
    ("Setup", _INFO, _Style.CYAN),
    ("Prepare", _INFO, _Style.CYAN),
    ("Configure", _INFO, _Style.CYAN),
    ("Run", _INFO, _Style.CYAN),
    ("Running", _INFO, _Style.CYAN),
    ("Exec", _INFO, _Style.CYAN),
    ("Execute", _INFO, _Style.CYAN),
    ("Step", _INFO, _Style.CYAN),
    ("Phase", _INFO, _Style.CYAN),
    ("Ready", _INFO, _Style.GREEN),
    ("Queued", _INFO, _Style.CYAN),
    ("Pending", _INFO, _Style.CYAN),
    ("Wait", _INFO, _Style.YELLOW),
    ("Waiting", _INFO, _Style.YELLOW),
    ("Blocked", _WARN, _Style.YELLOW),
    ("Progress", _INFO, _Style.CYAN),
    ("Retry", _WARN, _Style.YELLOW),
    ("Retrying", _WARN, _Style.YELLOW),
    ("Resume", _INFO, _Style.GREEN),
    ("Pause", _INFO, _Style.YELLOW),
    ("Skip", _INFO, _Style.YELLOW),
    ("Skipped", _INFO, _Style.YELLOW),
    ("Cancel", _WARN, _Style.YELLOW),
    ("Cancelled", _WARN, _Style.YELLOW),
    ("Timeout", _ERR, _Style.RED),
    ("Finish", _OK, _Style.GREEN),
    ("Finished", _OK, _Style.GREEN),
    ("Complete", _OK, _Style.GREEN),
    ("Completed", _OK, _Style.GREEN),
    ("Stop", _INFO, _Style.YELLOW),
    ("Stopped", _INFO, _Style.YELLOW),
    ("Reset", _INFO, _Style.CYAN),
    ("Cleanup", _INFO, _Style.CYAN),
    ("Shutdown", _INFO, _Style.YELLOW),
    ("Clone", _INFO, _Style.BLUE),
    ("Cloned", _OK, _Style.GREEN),
    ("Fetch", _INFO, _Style.BLUE),
    ("Fetched", _OK, _Style.GREEN),
    ("Pull", _INFO, _Style.BLUE),
    ("Push", _INFO, _Style.BLUE),
    ("Pushed", _OK, _Style.GREEN),
    ("Commit", _INFO, _Style.BLUE),
    ("Committed", _OK, _Style.GREEN),
    ("Checkout", _INFO, _Style.BLUE),
    ("Merge", _INFO, _Style.BLUE),
    ("Merged", _OK, _Style.GREEN),
    ("Rebase", _INFO, _Style.BLUE),
    ("Tag", _INFO, _Style.BLUE),
    ("Tagged", _OK, _Style.GREEN),
    ("Branch", _INFO, _Style.BLUE),
    ("Stash", _INFO, _Style.BLUE),
    ("Sync", _INFO, _Style.BLUE),
    ("Syncing", _INFO, _Style.BLUE),
    ("Synced", _OK, _Style.GREEN),
    ("Update", _INFO, _Style.BLUE),
    ("Updated", _OK, _Style.GREEN),
    ("Upgrade", _INFO, _Style.BLUE),
    ("Upgraded", _OK, _Style.GREEN),
    ("Install", _INFO, _Style.BLUE),
    ("Installed", _OK, _Style.GREEN),
    ("Uninstall", _INFO, _Style.YELLOW),
    ("Uninstalled", _OK, _Style.GREEN),
    ("Build", _INFO, _Style.BLUE),
    ("Built", _OK, _Style.GREEN),
    ("Compile", _INFO, _Style.BLUE),
    ("Compiled", _OK, _Style.GREEN),
    ("Link", _INFO, _Style.BLUE),
    ("Linked", _OK, _Style.GREEN),
    ("Assemble", _INFO, _Style.BLUE),
    ("Assembled", _OK, _Style.GREEN),
    ("Generate", _INFO, _Style.BLUE),
    ("Generated", _OK, _Style.GREEN),
    ("Test", _INFO, _Style.CYAN),
    ("Tested", _OK, _Style.GREEN),
    ("Lint", _INFO, _Style.CYAN),
    ("Linted", _OK, _Style.GREEN),
    ("Verify", _INFO, _Style.CYAN),
    ("Verified", _OK, _Style.GREEN),
    ("Validate", _INFO, _Style.CYAN),
    ("Validated", _OK, _Style.GREEN),
    ("Check", _INFO, _Style.CYAN),
    ("Checked", _OK, _Style.GREEN),
    ("Inspect", _INFO, _Style.CYAN),
    ("Inspected", _OK, _Style.GREEN),
    ("Deploy", _INFO, _Style.BLUE),
    ("Deployed", _OK, _Style.GREEN),
    ("Sign", _INFO, _Style.CYAN),
    ("Signed", _OK, _Style.GREEN),
    ("Pack", _INFO, _Style.BLUE),
    ("Packed", _OK, _Style.GREEN),
    ("Package", _INFO, _Style.BLUE),
    ("Packaged", _OK, _Style.GREEN),
    ("Compress", _INFO, _Style.BLUE),
    ("Compressed", _OK, _Style.GREEN),
    ("Extract", _INFO, _Style.BLUE),
    ("Extracted", _OK, _Style.GREEN),
    ("Download", _INFO, _Style.BLUE),
    ("Downloaded", _OK, _Style.GREEN),
    ("Upload", _INFO, _Style.BLUE),
    ("Uploaded", _OK, _Style.GREEN),
    ("Create", _INFO, _Style.CYAN),
    ("Created", _OK, _Style.GREEN),
    ("Write", _INFO, _Style.CYAN),
    ("Written", _OK, _Style.GREEN),
    ("Read", _INFO, _Style.CYAN),
    ("Copy", _INFO, _Style.CYAN),
    ("Copied", _OK, _Style.GREEN),
    ("Move", _INFO, _Style.CYAN),
    ("Moved", _OK, _Style.GREEN),
    ("Rename", _INFO, _Style.CYAN),
    ("Renamed", _OK, _Style.GREEN),
    ("Delete", _INFO, _Style.YELLOW),
    ("Deleted", _OK, _Style.GREEN),
    ("Remove", _INFO, _Style.YELLOW),
    ("Removed", _OK, _Style.GREEN),
    ("Clean", _INFO, _Style.CYAN),
    ("Cleaned", _OK, _Style.GREEN),
    ("Load", _INFO, _Style.CYAN),
    ("Loaded", _OK, _Style.GREEN),
    ("Save", _INFO, _Style.CYAN),
    ("Saved", _OK, _Style.GREEN),
    ("Parse", _INFO, _Style.CYAN),
    ("Parsed", _OK, _Style.GREEN),
    ("Convert", _INFO, _Style.CYAN),
    ("Converted", _OK, _Style.GREEN),
    ("Apply", _INFO, _Style.CYAN),
    ("Applied", _OK, _Style.GREEN),
    ("Patch", _INFO, _Style.BLUE),
    ("Patched", _OK, _Style.GREEN),
    ("Mount", _INFO, _Style.CYAN),
    ("Mounted", _OK, _Style.GREEN),
    ("Unmount", _INFO, _Style.YELLOW),
    ("Unmounted", _OK, _Style.GREEN),
    ("Format", _INFO, _Style.CYAN),
    ("Formatted", _OK, _Style.GREEN),
    ("Connect", _INFO, _Style.BLUE),
    ("Connected", _OK, _Style.GREEN),
    ("Disconnect", _INFO, _Style.YELLOW),
    ("Disconnected", _WARN, _Style.YELLOW),
    ("Reconnect", _INFO, _Style.BLUE),
    ("Reconnected", _OK, _Style.GREEN),
    ("Online", _OK, _Style.GREEN),
    ("Offline", _WARN, _Style.YELLOW),
    ("Listen", _INFO, _Style.BLUE),
    ("Listening", _INFO, _Style.BLUE),
    ("Auth", _INFO, _Style.MAGENTA),
    ("Authenticated", _OK, _Style.GREEN),
    ("Login", _INFO, _Style.MAGENTA),
    ("Logout", _INFO, _Style.MAGENTA),
    ("Denied", _ERR, _Style.RED),
    ("Granted", _OK, _Style.GREEN),
    ("Permission", _WARN, _Style.YELLOW),
    ("Lock", _INFO, _Style.YELLOW),
    ("Locked", _WARN, _Style.YELLOW),
    ("Unlock", _INFO, _Style.CYAN),
    ("Unlocked", _OK, _Style.GREEN),
    ("Encrypt", _INFO, _Style.MAGENTA),
    ("Decrypt", _INFO, _Style.MAGENTA),
    ("Hash", _INFO, _Style.CYAN),
    ("Found", _OK, _Style.GREEN),
    ("NotFound", _WARN, _Style.YELLOW),
    ("Exists", _INFO, _Style.CYAN),
    ("Missing", _ERR, _Style.RED),
    ("Hit", _OK, _Style.GREEN),
    ("Miss", _WARN, _Style.YELLOW),
    ("Match", _OK, _Style.GREEN),
    ("Matched", _OK, _Style.GREEN),
    ("Mismatch", _WARN, _Style.YELLOW),
    ("Changed", _INFO, _Style.YELLOW),
    ("Unchanged", _INFO, _Style.CYAN),
    ("Added", _OK, _Style.GREEN),
    ("New", _INFO, _Style.CYAN),
    ("Expired", _WARN, _Style.YELLOW),
    ("Stale", _WARN, _Style.YELLOW),
    ("Uptodate", _OK, _Style.GREEN),
    ("Outdated", _WARN, _Style.YELLOW),
)

_STATUS_ALIASES: dict[str, Status] = {
    "ok": _status("Ok", _OK, _Style.GREEN),
    "warn": _status("Warn", _WARN, _Style.YELLOW),
    "err": _status("Error", _ERR, _Style.RED),
    "fatal": _status("Fatal", _FATAL, _Style.MAGENTA),
    "done": _status("Done", _OK, _Style.GREEN),
    "success": _status("Success", _OK, _Style.GREEN),
}

STATUSES: dict[str, Status] = {spec[0]: _status(*spec) for spec in _STATUS_DEFS}

_LOWERCASE_STATUSES: dict[str, Status] = {}
for _canonical in STATUSES.values():
    _LOWERCASE_STATUSES.setdefault(_canonical.name.lower(), _canonical)
_LOWERCASE_STATUSES.update(_STATUS_ALIASES)


class _SafeDict(dict):
    """dict that renders unknown format placeholders as an empty string."""

    def __missing__(self, key: str) -> str:
        return ""


class Logger:
    """Terminal logger with named statuses and a configurable line format."""

    def __init__(
        self,
        verbose: bool = False,
        stream: TextIO | None = None,
        no_color: bool | None = None,
        fmt: str | None = None,
        timestamp_format: str | None = None,
        program: str = "cru",
    ) -> None:
        self.verbose = verbose
        self.stream = stream if stream is not None else sys.stdout
        self.no_color = self._color_disabled() if no_color is None else no_color
        self.fmt = DEFAULT_FORMAT if fmt is None else fmt
        self.timestamp_format = (
            DEFAULT_TIMESTAMP_FORMAT if timestamp_format is None else timestamp_format
        )
        self.program = program
        self._statuses = dict(_LOWERCASE_STATUSES)
        self._started = time.monotonic()
        self._counter = 0

    @staticmethod
    def _color_disabled() -> bool:
        if os.environ.get("NO_COLOR"):
            return True
        try:
            return not sys.stdout.isatty()
        except (AttributeError, ValueError):
            return True

    def _resolve(self, status: str | Status) -> Status:
        if isinstance(status, Status):
            return status
        name = str(status)
        found = self._statuses.get(name.lower())
        if found is not None:
            return found
        return Status(name=name, level=LogLevel.INFO, color=_Style.CYAN, label=name)

    def _emit(self, status: str | Status, message: str, **fields: object) -> None:
        resolved = self._resolve(status)
        if resolved.level < LogLevel.INFO and not self.verbose:
            return
        color = resolved.color if (resolved.color and not self.no_color) else ""
        reset = _Style.RESET if color else ""
        base = {
            "ts": time.strftime(self.timestamp_format),
            "time": time.strftime(self.timestamp_format),
            "date": time.strftime("%Y-%m-%d"),
            "status": resolved.label or resolved.name,
            "label": resolved.label or resolved.name,
            "level": resolved.level.name,
            "message": message,
            "msg": message,
            "program": self.program,
            "pid": os.getpid(),
            "hostname": platform.node(),
            "counter": self._counter,
            "elapsed": f"{int(time.monotonic() - self._started)}s",
            "color": color,
            "reset": reset,
            "bold": _Style.BOLD if color else "",
            "dim": _Style.DIM if color else "",
            **fields,
        }
        self._counter += 1
        if not self.fmt:
            line = message
        else:
            try:
                line = self.fmt.format_map(_SafeDict(base))
            except (KeyError, ValueError, IndexError):
                line = message
        print(line, file=self.stream, flush=True)

    def emit(self, status: str | Status, message: str, **fields: object) -> None:
        self._emit(status, message, **fields)

    def status(self, name: str, message: str, **fields: object) -> None:
        self._emit(name, message, **fields)

    def debug(self, message: str) -> None:
        self._emit("Debug", message)

    def info(self, message: str) -> None:
        self._emit("Info", message)

    def success(self, message: str) -> None:
        self._emit("Ok", message)

    def warning(self, message: str) -> None:
        self._emit("Warn", message)

    def error(self, message: str) -> None:
        self._emit("Error", message)

    def critical(self, message: str) -> None:
        self._emit("Fatal", message)

    def raw(self, message: str, color: str = "") -> None:
        if not message:
            return
        if self.no_color or not color:
            print(message, file=self.stream, flush=True)
        else:
            print(f"{color}{message}{_Style.RESET}", file=self.stream, flush=True)

    def raw_dim(self, message: str) -> None:
        self.raw(message, _Style.DIM)

    def raw_warn(self, message: str) -> None:
        self.raw(message, _Style.YELLOW)

    def raw_error(self, message: str) -> None:
        self.raw(message, _Style.RED)

    def raw_success(self, message: str) -> None:
        self.raw(message, _Style.GREEN)

    def raw_color(self, message: str, color: str | object) -> None:
        self.raw(message, color_code(color))

    def apply(
        self,
        settings: dict,
        verbose: bool | None = None,
        no_color: bool | None = None,
    ) -> None:
        general = settings.get("general") or {}
        log_cfg = settings.get("log") or {}
        if general.get("program"):
            self.program = str(general["program"])
        if log_cfg.get("format") is not None:
            self.fmt = str(log_cfg["format"])
        if log_cfg.get("timestamp_format") is not None:
            self.timestamp_format = str(log_cfg["timestamp_format"])
        if verbose is not None:
            self.verbose = bool(verbose)
        elif log_cfg.get("verbose") is not None:
            self.verbose = bool(log_cfg["verbose"])
        if no_color is not None:
            self.no_color = bool(no_color)
        elif log_cfg.get("no_color") is not None:
            self.no_color = bool(log_cfg["no_color"])
        for key, override in (log_cfg.get("statuses") or {}).items():
            current = self._statuses.get(str(key).lower())
            if current is None or not isinstance(override, dict):
                continue
            label = str(override.get("label")) if override.get("label") else current.label
            color = color_code(override.get("color")) if override.get("color") else current.color
            updated = replace(current, label=label, color=color)
            self._statuses[updated.name.lower()] = updated
        return self

    def __getitem__(self, name: str) -> object:
        return self._emitter_for(name)

    def __getattr__(self, name: str) -> object:
        if name.startswith("_"):
            raise AttributeError(name)
        return self._emitter_for(name)

    def _emitter_for(self, name: str) -> object:
        found = self._statuses.get(name.lower())
        if found is None:
            raise AttributeError(name)

        def emit(message: str, **fields: object) -> None:
            self._emit(found, message, **fields)

        return emit


log = Logger()


def configure_logger(
    verbose: bool | None = None,
    no_color: bool | None = None,
    settings: dict | None = None,
) -> Logger:
    """Apply the user config (config.toml) then CLI overrides to the logger."""
    if settings is None:
        from cruine.config.settings import load_settings

        settings = load_settings()
    log.apply(settings, verbose=verbose, no_color=no_color)
    return log
