"""Cruine user configuration (``~/.config/cruine/config.toml``).

The config file is optional. When present it overrides the built-in
defaults; anything left out falls back to the defaults. The path can be
overridden with the ``CRUINE_CONFIG`` environment variable (used by tests
and useful for per-project setups).

Everything about output formatting is configurable here: the log line
format (any string, with ``{variable}`` placeholders), the timestamp
pattern, per-status labels and colours, plus general options such as the
program name used by the ``{program}`` format variable.
"""

from __future__ import annotations

import os
from pathlib import Path

import tomllib

CONFIG_ENV = "CRUINE_CONFIG"

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "cruine"
DEFAULT_CONFIG_FILENAME = "config.toml"

DEFAULT_SETTINGS: dict = {
    "general": {"program": "cru"},
    "log": {
        "format": "[{ts}] [{color}{status}{reset}] {message}",
        "timestamp_format": "%H:%M:%S",
        "verbose": False,
        "no_color": False,
        "statuses": {},
    },
}

CONFIG_TEMPLATE = """\
# Cruine configuration (usually ~/.config/cruine/config.toml)
# Optional: every key shown here is a default, so you only need to write
# the values you want to change.

[general]
# Program name used by the {program} variable in log formats.
program = "cru"

[log]
# Line format. Any string is accepted. Placeholders:
#   {ts} {time} {date} {status} {label} {level} {message} {msg}
#   {program} {pid} {hostname} {counter} {elapsed}
#   {color} {reset} {bold} {dim}
# Use "" to print bare messages. Unknown placeholders render empty.
format = "[{ts}] [{color}{status}{reset}] {message}"

# strftime pattern for {ts}/{time} (24-hour clock by default).
timestamp_format = "%H:%M:%S"

# Defaults; the -v / --verbose and --no-color flags override these.
verbose = false
no_color = false

[log.statuses]
# Override the label and/or colour of any status (see `cru config`).
# Available colours: black red green yellow blue magenta cyan white gray,
# bright_red bright_green bright_yellow bright_blue bright_magenta
# bright_cyan bright_white, and modifiers bold / dim / underline.
#   Info  = { label = "Info",  color = "cyan" }
#   Build = { label = "BUILD", color = "bright_blue" }
"""


def config_dir() -> Path:
    return DEFAULT_CONFIG_DIR


def config_path() -> Path:
    env = os.environ.get(CONFIG_ENV)
    if env:
        return Path(env)
    return DEFAULT_CONFIG_DIR / DEFAULT_CONFIG_FILENAME


def _merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _clone(value: object) -> object:
    if isinstance(value, dict):
        return {k: _clone(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clone(item) for item in value]
    return value


def load_settings(path: str | os.PathLike[str] | None = None) -> dict:
    """Load, parse and merge the user config with the built-in defaults."""
    settings = _clone(DEFAULT_SETTINGS)
    target = Path(path) if path is not None else config_path()
    if not target.is_file():
        return settings
    try:
        with target.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError, ValueError):
        raw = {}
    if isinstance(raw, dict):
        settings = _merge(settings, raw)
    return settings


def write_template(path: str | os.PathLike[str] | None = None) -> Path:
    """Write an example config.toml; raises FileExistsError if it exists."""
    target = Path(path) if path is not None else config_path()
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite existing config: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    return target


def format_config(settings: dict) -> str:
    """Render the effective settings as a small human-readable report."""
    general = settings.get("general") or {}
    log_cfg = settings.get("log") or {}
    statuses = log_cfg.get("statuses") or {}
    lines = [
        f"program         : {general.get('program', 'cru')}",
        f"log.format      : {log_cfg.get('format', '')!r}",
        f"log.timestamp   : {log_cfg.get('timestamp_format', '')!r}",
        f"log.verbose     : {bool(log_cfg.get('verbose'))}",
        f"log.no_color    : {bool(log_cfg.get('no_color'))}",
        f"log.statuses    : {len(statuses)} override(s)",
    ]
    if statuses:
        lines.append("overrides       :")
        for key, override in sorted(statuses.items()):
            label = override.get("label") if isinstance(override, dict) else None
            color = override.get("color") if isinstance(override, dict) else None
            bits = []
            if label:
                bits.append(f"label={label}")
            if color:
                bits.append(f"color={color}")
            lines.append(f"  {key:<16} {', '.join(bits) or '(none)'}")
    return "\n".join(lines)
