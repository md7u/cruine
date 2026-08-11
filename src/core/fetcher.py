"""ROM source acquisition: native manifest sync plus device trees."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from cruine.core.syncer import ManifestSyncer
from cruine.models.device import RepositoryModel
from cruine.models.recipe import RecipeSchema
from cruine.utils.logger import log
from cruine.utils.urls import localize_url


class FetchError(RuntimeError):
    """Raised when source acquisition fails."""


class SourceFetcher:
    """Pulls the ROM source: native manifest sync, then per-device trees.

    The full ROM source tree (every active project in the ROM manifest) is
    synced natively by :class:`~cruine.core.syncer.ManifestSyncer` — no
    ``repo`` binary is required. Per-device repositories and plain local
    files declared in the recipe are then laid on top.
    """

    MAX_ATTEMPTS = 3
    RETRY_DELAY_SECONDS = 5

    def __init__(
        self,
        recipe: RecipeSchema,
        workspace: Path,
        jobs: int | None = None,
    ) -> None:
        self.recipe = recipe
        self.workspace = Path(workspace)
        self.jobs = jobs or (os.cpu_count() or 1)

    def fetch(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._sync_manifest()
        self._clone_device_trees()
        self._copy_local_files()
        log.success(f"Source trees ready in {self.workspace}")

    def _sync_manifest(self) -> None:
        if (self.workspace / ".repo").exists():
            log.info(
                "Found .repo/ from a previous repo workflow; "
                "Cruine syncs natively and will not touch it"
            )
        syncer = ManifestSyncer(self.recipe, self.workspace, jobs=self.jobs)
        syncer.sync()

    def _clone_device_trees(self) -> None:
        for repository in self.recipe.device.repositories:
            self._clone_repository(repository)

    def _clone_repository(self, repository: RepositoryModel) -> None:
        destination = self.workspace / repository.target_path
        if destination.exists() and (destination / ".git").exists():
            log.info(f"Already cloned: {repository.url} -> {destination}")
            return
        if destination.exists():
            log.warning(f"Removing stale path (not a git clone) before cloning: {destination}")
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        destination.parent.mkdir(parents=True, exist_ok=True)
        log.info(f"Cloning {repository.type} tree: {repository.url}")
        command = [
            "git",
            "clone",
            "--depth=1",
            "--single-branch",
            localize_url(repository.url),
            str(destination),
        ]
        self._run_retry(command, f"clone {repository.url}")

    def _copy_local_files(self) -> None:
        for item in self.recipe.device.files:
            source = Path(localize_url(item.url)).expanduser()
            if not source.exists():
                raise FetchError(f"Local source path does not exist: {source}")
            destination = self.workspace / item.target_path
            if destination.exists():
                log.warning(f"Target already exists, removing: {destination}")
                if destination.is_dir() and not destination.is_symlink():
                    shutil.rmtree(destination)
                else:
                    destination.unlink()
            destination.parent.mkdir(parents=True, exist_ok=True)
            log.info(f"Copying {item.type} files: {source} -> {destination}")
            if source.is_dir():
                shutil.copytree(source, destination, symlinks=True)
            else:
                shutil.copy2(source, destination)

    def _run_retry(self, command: list[str], label: str) -> None:
        last_code = -1
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            log.info(f"{label} (attempt {attempt}/{self.MAX_ATTEMPTS})")
            try:
                proc = subprocess.Popen(
                    command,
                    cwd=str(self.workspace),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except FileNotFoundError as exc:
                raise FetchError(f"Required tool not found for {label}: {exc}") from exc
            assert proc.stdout is not None
            for line in proc.stdout:
                log.raw(line.rstrip())
            proc.wait()
            last_code = proc.returncode
            if last_code == 0:
                log.success(f"{label} completed")
                return
            if attempt < self.MAX_ATTEMPTS:
                log.warning(
                    f"{label} failed (exit {last_code}); retrying in {self.RETRY_DELAY_SECONDS}s"
                )
                time.sleep(self.RETRY_DELAY_SECONDS)
        raise FetchError(
            f"{label} failed after {self.MAX_ATTEMPTS} attempts (exit code {last_code})"
        )
