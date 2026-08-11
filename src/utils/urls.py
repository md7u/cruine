"""Source URL helpers for local (file://) and archive inputs."""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

__all__ = ["localize_url", "normalize_url", "strip_archive_suffix"]

_SCP_LIKE_RE = re.compile(r"^[^/:]+@[^/:]+:[^/]+")


def normalize_url(url: str) -> str:
    """Normalize a git URL to a form ``urljoin`` can reason about.

    Trailing slashes are removed and SCP-like URLs (``git@host:path``) are
    converted to their equivalent ``ssh://git@host/path`` form, matching the
    behaviour of the AOSP manifest tools. Any other form — https, ssh, git,
    ``file://``, or a plain filesystem path — is returned unchanged.
    """
    value = (url or "").strip().rstrip("/")
    if not value:
        return value
    parsed = urllib.parse.urlparse(value)
    if not parsed.scheme and _SCP_LIKE_RE.match(value):
        return "ssh://" + value.replace(":", "/", 1)
    return value


def localize_url(url: str) -> str:
    """Strip a leading ``file://`` scheme so the result is a usable path.

    ``file:///abs/path`` becomes ``/abs/path`` and ``file://rel/path``
    becomes ``rel/path``. Any other URL (http, ssh, git, ...) is returned
    unchanged. Plain local paths already pass through untouched.
    """
    value = (url or "").strip()
    if value.startswith("file://"):
        return value[len("file://") :]
    return value


def strip_archive_suffix(name: str) -> str:
    """Remove a known archive suffix from a filename, leaving the stem.

    Multi-dot suffixes (``.tar.gz``, ``.tar.xz``) are removed as a unit so
    ``LineageOS.tar.gz`` becomes ``LineageOS`` rather than ``LineageOS.tar``.
    Unknown suffixes are left untouched.
    """
    value = name or ""
    lower = value.lower()
    for suffix in (".tar.gz", ".tar.xz", ".tar.bz2", ".tar.bz", ".tar.zst"):
        if lower.endswith(suffix):
            return value[: -len(suffix)]
    return str(Path(value).with_suffix(""))
