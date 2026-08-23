"""Subprocess helper: run commands with retries and streamed output."""

from __future__ import annotations

import shutil
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path

from cruine.utils.logger import log

__all__ = ["CommandError", "run_retry"]


class CommandError(RuntimeError):
    """Raised when a retried command fails on every attempt."""


def run_retry(
    command: Sequence[str],
    label: str,
    cwd: str | Path | None = None,
    max_attempts: int = 3,
    retry_delay_seconds: float = 5.0,
    retry_cleanup_path: str | Path | None = None,
) -> None:
    """Run ``command`` streaming output, retrying up to ``max_attempts``.

    Raises :class:`CommandError` if every attempt fails. A missing binary
    fails immediately without retries.

    ``retry_cleanup_path`` names the directory a clone operation creates.
    When the path did not exist before the first attempt (i.e. this
    invocation owns it), a failed attempt removes any partial leftovers so
    the next attempt does not hit "destination path already exists".
    """
    last_code = -1
    owned_dest: Path | None = None
    if retry_cleanup_path is not None:
        dest = Path(retry_cleanup_path)
        if not dest.exists():
            owned_dest = dest
    for attempt in range(1, max_attempts + 1):
        log.info(f"{label} (attempt {attempt}/{max_attempts})")
        try:
            proc = subprocess.Popen(
                list(command),
                cwd=str(cwd) if cwd is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise CommandError(f"Required tool not found for {label}: {exc}") from exc
        assert proc.stdout is not None
        for line in proc.stdout:
            log.raw(line.rstrip())
        proc.wait()
        last_code = proc.returncode
        if last_code == 0:
            log.success(f"{label} completed")
            return
        if attempt < max_attempts:
            _remove_partial(owned_dest)
            log.warning(f"{label} failed (exit {last_code}); retrying in {retry_delay_seconds}s")
            time.sleep(retry_delay_seconds)
    raise CommandError(f"{label} failed after {max_attempts} attempts (exit code {last_code})")


def _remove_partial(path: Path | None) -> None:
    """Remove a partially created destination between retries."""
    if path is None or not path.exists():
        return
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError as exc:
        log.warning(f"Could not clean partial path {path}: {exc}")
