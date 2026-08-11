"""Tests for the build executor."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
from cruine.core.executor import BuildError, BuildExecutor
from cruine.models.recipe import RecipeSchema


def _recipe() -> RecipeSchema:
    return RecipeSchema(
        project_name="TestROM",
        rom={
            "source": "https://example.com/android.git",
            "branch": "b",
            "lunch_prefix": "test",
            "build_target": "bacon",
        },
        device={
            "codename": "testdevice",
            "repositories": [
                {"type": "device", "url": "https://e.com/d.git", "target_path": "device/x/a"}
            ],
        },
        options={"use_ccache": False},
    )


def test_build_prefers_cru_jobs() -> None:
    recipe = _recipe()
    recipe.options.parallel_jobs = 8
    with mock.patch.object(BuildExecutor, "run") as run_mock:
        BuildExecutor(recipe, Path("/tmp/ws")).build({"CRU_JOBS": "16"})
    script = run_mock.call_args.args[0]
    assert "mka bacon -j16" in script


def test_build_script_structure() -> None:
    recipe = _recipe()
    with mock.patch.object(BuildExecutor, "run") as run_mock:
        BuildExecutor(recipe, Path("/tmp/ws")).build({"CRU_JOBS": "4"})
    script = run_mock.call_args.args[0]
    assert "source build/envsetup.sh" in script
    assert "lunch test_testdevice-userdebug" in script
    assert "mka bacon -j4" in script


def test_build_clean_adds_clean_step() -> None:
    recipe = _recipe()
    with mock.patch.object(BuildExecutor, "run") as run_mock:
        BuildExecutor(recipe, Path("/tmp/ws")).build({"CRU_JOBS": "4"}, clean=True)
    script = run_mock.call_args.args[0]
    assert "mka clean" in script


def test_run_success(tmp_path: Path) -> None:
    executor = BuildExecutor(_recipe(), tmp_path)
    assert executor.run("exit 0") == 0


def test_run_failure_raises(tmp_path: Path) -> None:
    executor = BuildExecutor(_recipe(), tmp_path)
    with pytest.raises(BuildError):
        executor.run("exit 1")


def test_run_uses_devnull_stdin(tmp_path: Path) -> None:
    """lunch must never block on interactive prompts, so stdin is /dev/null."""
    from cruine.core.executor import subprocess as executor_subprocess

    captured = {}

    class _FakePopen:
        def __init__(self, *args, **kwargs) -> None:
            captured["kwargs"] = kwargs
            self.stdout = []
            self.returncode = 0

        def wait(self) -> None:
            pass

    with mock.patch.object(executor_subprocess, "Popen", _FakePopen):
        BuildExecutor(_recipe(), tmp_path).run("lunch combo", env={})
    assert captured["kwargs"]["stdin"] == executor_subprocess.DEVNULL


def test_build_mem_limit_prepends_ulimit() -> None:
    recipe = _recipe()
    with mock.patch.object(BuildExecutor, "run") as run_mock:
        BuildExecutor(recipe, Path("/tmp/ws"), mem_limit_mb=4096).build({"CRU_JOBS": "4"})
    script = run_mock.call_args.args[0]
    assert script.startswith("ulimit -v 4194304; cd")
