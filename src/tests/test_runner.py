"""Tests for the retried command runner."""

from __future__ import annotations

from pathlib import Path

import pytest
from cruine.utils.runner import CommandError, run_retry


def test_retry_removes_partial_clone_destination(tmp_path: Path) -> None:
    """A failed attempt removes the partial destination it created so the
    next attempt does not fail with "destination path already exists"."""
    dest = tmp_path / "clone-target"
    marker = tmp_path / "attempt-marker"
    script = (
        f"if [ ! -f {marker} ]; then touch {marker}; mkdir -p {dest}; exit 1; fi; "
        f"if [ -d {dest} ]; then exit 2; fi; mkdir -p {dest}; exit 0"
    )
    run_retry(
        ["bash", "-c", script],
        "clone test",
        max_attempts=3,
        retry_delay_seconds=0,
        retry_cleanup_path=dest,
    )
    assert marker.is_file()
    assert dest.is_dir()


def test_retry_never_removes_pre_existing_destination(tmp_path: Path) -> None:
    """A destination that existed before the first attempt belongs to the
    caller and must survive failed retries untouched."""
    dest = tmp_path / "owned"
    dest.mkdir()
    (dest / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(CommandError):
        run_retry(
            ["bash", "-c", f"touch {dest}/partial && exit 1"],
            "clone test",
            max_attempts=2,
            retry_delay_seconds=0,
            retry_cleanup_path=dest,
        )
    assert (dest / "keep.txt").is_file()
