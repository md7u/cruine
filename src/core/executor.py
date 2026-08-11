"""Subprocess execution and build orchestration."""

from __future__ import annotations

import contextlib
import os
import shlex
import signal
import subprocess
import time
from pathlib import Path
from typing import TextIO

from cruine.models.recipe import RecipeSchema
from cruine.utils.log_parser import LogParser
from cruine.utils.logger import log


class BuildError(RuntimeError):
    """Raised when a build command exits with a non-zero status."""


class BuildExecutor:
    """Spawns the AOSP build pipeline and streams output in real time."""

    def __init__(
        self,
        recipe: RecipeSchema,
        workspace: Path,
        log_file: Path | None = None,
        mem_limit_mb: int | None = None,
    ) -> None:
        self.recipe = recipe
        self.workspace = Path(workspace)
        self.log_file = Path(log_file) if log_file is not None else None
        self.mem_limit_mb = mem_limit_mb

    def run(self, command: str, env: dict[str, str] | None = None) -> int:
        parser = LogParser(logger=log)
        env = env if env is not None else os.environ.copy()
        start = time.monotonic()
        log.info(f"$ {command}")
        proc = subprocess.Popen(
            command,
            shell=True,
            executable="/bin/bash",
            cwd=str(self.workspace),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        assert proc.stdout is not None
        if self.log_file is None:
            self._drain(proc, parser)
        else:
            with open(self.log_file, "a", encoding="utf-8") as handle:
                self._drain(proc, parser, handle)
        elapsed = int(time.monotonic() - start)
        parser.summary()
        if proc.returncode != 0:
            raise BuildError(f"Build command exited with code {proc.returncode} after {elapsed}s")
        log.success(f"Command completed in {elapsed}s")
        return proc.returncode

    @staticmethod
    def _drain(
        proc: subprocess.Popen[str],
        parser: LogParser,
        handle: TextIO | None = None,
    ) -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            stripped = line.rstrip("\n")
            parser.evaluate(stripped)
            if handle is not None:
                handle.write(line)
            if parser.is_fatal(stripped):
                log.warning("Fatal build error detected, terminating build...")
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                break
        proc.wait()

    def build(self, env: dict[str, str], clean: bool = False) -> None:
        options = self.recipe.options
        lunch = self.recipe.lunch_combo()
        jobs = int(env.get("CRU_JOBS") or options.parallel_jobs or os.cpu_count() or 1)

        script = [f"cd {shlex.quote(str(self.workspace))}"]
        script.append("source build/envsetup.sh")
        if clean:
            log.info("Cleaning previous build output (mka clean)")
            script.append("mka clean >/dev/null 2>&1 || make clean >/dev/null 2>&1 || true")
        script.append(f"lunch {lunch}")
        build_command = f"mka {self.recipe.rom.build_target} -j{jobs}"
        for extra in options.extra_make_args:
            build_command += f" {extra}"
        script.append(build_command)

        joined = " && ".join(script)
        if self.mem_limit_mb:
            joined = f"ulimit -v {self.mem_limit_mb * 1024}; {joined}"
        log.info(f"Lunch combo: {lunch} | jobs: {jobs} | target: {self.recipe.rom.build_target}")
        self.run(joined, env=env)
