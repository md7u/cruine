"""Subprocess helper: run commands with retries and streamed output."""

from __future__ import annotations

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
) -> None:
    """Run ``command`` streaming output, retrying up to ``max_attempts``.

    Raises :class:`CommandError` if every attempt fails. A missing binary
    fails immediately without retries.
    """
    last_code = -1
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
            log.warning(f"{label} failed (exit {last_code}); retrying in {retry_delay_seconds}s")
            time.sleep(retry_delay_seconds)
    raise CommandError(f"{label} failed after {max_attempts} attempts (exit code {last_code})")
