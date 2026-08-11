"""Automated tree patching and hooks."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from cruine.models.patch import PatchModel
from cruine.models.recipe import RecipeSchema
from cruine.utils.logger import log


class PatchError(RuntimeError):
    """Raised when a patch or hook fails."""


class Patcher:
    """Applies patch files and runs lifecycle hooks against the tree."""

    def __init__(self, recipe: RecipeSchema, workspace: Path) -> None:
        self.recipe = recipe
        self.workspace = Path(workspace)

    def apply_patches(self) -> None:
        for patch in self.recipe.patches:
            self._apply_patch(patch)
        if self.recipe.patches:
            log.success(f"Applied {len(self.recipe.patches)} patch(es)")

    def _apply_patch(self, patch: PatchModel) -> None:
        patch_file = Path(patch.file).expanduser()
        if not patch_file.is_file():
            raise PatchError(f"Patch file does not exist: {patch_file}")
        apply_dir = self.workspace / patch.directory
        if not apply_dir.is_dir():
            raise PatchError(f"Patch target directory does not exist: {apply_dir}")
        log.info(f"Applying patch {patch_file.name} in {apply_dir}")
        if shutil.which("git"):
            result = subprocess.run(
                ["git", "apply", f"-p{patch.strip}", str(patch_file)],
                cwd=str(apply_dir),
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            result = None
        if result is None or result.returncode != 0:
            patch_bin = shutil.which("patch")
            if not patch_bin:
                raise PatchError(
                    "git apply failed and the 'patch' command is unavailable: "
                    f"{(result.stderr if result else '').strip()}"
                )
            log.warning("git apply failed, falling back to patch(1)")
            result = subprocess.run(
                [patch_bin, f"-p{patch.strip}", "-i", str(patch_file)],
                cwd=str(apply_dir),
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                raise PatchError(
                    f"Failed to apply patch {patch_file}: {(result.stderr or '').strip()}"
                )
        log.success(f"Patch applied: {patch_file.name}")

    def run_hooks(self, phase: str) -> None:
        hooks = [hook for hook in self.recipe.hooks if hook.phase == phase]
        for hook in hooks:
            log.info(f"Hook [{phase}] {hook.name}: {hook.command}")
            cwd = self.workspace / hook.workdir if hook.workdir != "." else self.workspace
            proc = subprocess.run(hook.command, shell=True, cwd=str(cwd), check=False)
            if proc.returncode != 0:
                raise PatchError(f"Hook '{hook.name}' failed with exit code {proc.returncode}")
            log.success(f"Hook completed: {hook.name}")
