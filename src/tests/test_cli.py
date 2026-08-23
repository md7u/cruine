"""Tests for the CLI entry point and pipeline orchestration."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import ClassVar

import cruine.cli as cli
import pytest
from cruine.cli import PipelineOptions, run_pipeline

GIT = shutil.which("git")
requires_git = pytest.mark.skipif(GIT is None, reason="git not available")


def _git(*args: str, cwd: Path) -> None:
    subprocess.run([GIT, *args], cwd=cwd, check=True, capture_output=True)


def _make_repo(path: Path, content: str = "hello") -> Path:
    path.mkdir(parents=True)
    _git("init", "-b", "main", cwd=path)
    _git("config", "user.email", "test@cruine.dev", cwd=path)
    _git("config", "user.name", "Cruine Test", cwd=path)
    (path / "file.txt").write_text(content, encoding="utf-8")
    _git("add", ".", cwd=path)
    _git("commit", "-m", "initial", cwd=path)
    return path


def _make_manifest_repo(base: Path, body: str) -> Path:
    repo = _make_repo(base / "manifests")
    (repo / "default.xml").write_text(body, encoding="utf-8")
    _git("add", ".", cwd=repo)
    _git("commit", "-m", "manifest", cwd=repo)
    return repo


def test_main_tree_dispatch(capsys) -> None:
    assert cli.main(["version"]) == 0
    assert "Cruine" in capsys.readouterr().out


def test_main_parse_error_returns_code(capsys) -> None:
    assert cli.main([]) == 2
    assert cli.main(["-j", "abc"]) == 2


def test_main_version_flag(capsys) -> None:
    assert cli.main(["--version"]) == 0
    assert "Cruine" in capsys.readouterr().out


def test_main_generate_template(tmp_path, capsys) -> None:
    target = tmp_path / "rc.json"
    assert cli.main(["--generate-template", str(target)]) == 0
    assert target.is_file()


def test_run_pipeline_dry_run(sample_recipe, tmp_path, monkeypatch) -> None:
    (tmp_path / "rc.json").write_text(json.dumps(sample_recipe), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    opts = PipelineOptions(destination=tmp_path / "out", dry_run=True)
    assert run_pipeline(opts) == 0


def test_run_pipeline_dry_run_prints_jobs(sample_recipe, tmp_path, monkeypatch) -> None:
    import io

    from cruine.utils.logger import log

    recipe = json.loads(json.dumps(sample_recipe))
    recipe["options"] = {"use_ccache": False, "parallel_jobs": 8}
    (tmp_path / "rc.json").write_text(json.dumps(recipe), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    stream = io.StringIO()
    monkeypatch.setattr(log, "stream", stream)
    opts = PipelineOptions(destination=tmp_path / "out", dry_run=True)
    assert run_pipeline(opts) == 0
    assert "Jobs         : 8" in stream.getvalue()


def test_run_pipeline_rejects_file_destination(sample_recipe, tmp_path, monkeypatch) -> None:
    (tmp_path / "rc.json").write_text(json.dumps(sample_recipe), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    destination = tmp_path / "afile"
    destination.write_text("x", encoding="utf-8")
    opts = PipelineOptions(destination=destination)
    assert run_pipeline(opts) == 1


def test_pipeline_options_defaults() -> None:
    opts = PipelineOptions(destination="out")
    assert opts.jobs is None
    assert opts.skip_fetch is False
    assert opts.clean is False


def test_run_pipeline_skip_fetch_still_runs_hooks_and_patches(
    sample_recipe, tmp_path, monkeypatch
) -> None:
    """Legacy --skip-fetch must behave like repack mode: post_fetch hooks and
    patches still run so the tree is not left unpatched."""
    from unittest import mock

    from cruine.core.environment import EnvironmentManager
    from cruine.core.executor import BuildExecutor
    from cruine.core.packager import OutputPackager

    patch_file = tmp_path / "tree.patch"
    patch_file.write_text(
        "--- a/file.txt\n"
        "+++ b/file.txt\n"
        "@@ -1 +1 @@\n"
        "-hello\n"
        "+patched\n",
        encoding="utf-8",
    )
    recipe = json.loads(json.dumps(sample_recipe))
    recipe["patches"] = [{"file": str(patch_file), "directory": "tree"}]
    recipe["hooks"] = [
        {"name": "hooked", "command": "echo hooked > hooked.txt", "phase": "post_fetch"}
    ]
    (tmp_path / "rc.json").write_text(json.dumps(recipe), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    workspace = tmp_path / "TestROM"
    tree = workspace / "tree"
    tree.mkdir(parents=True)
    (tree / "file.txt").write_text("hello\n", encoding="utf-8")

    class _ReadyReport:
        ready = True
        recommended_jobs = 4
        missing_required: ClassVar[list[str]] = []

    with (
        mock.patch.object(EnvironmentManager, "validate", return_value=_ReadyReport()),
        mock.patch.object(BuildExecutor, "build"),
        mock.patch.object(OutputPackager, "package", return_value=tmp_path / "artifact.zip"),
    ):
        opts = PipelineOptions(destination=tmp_path / "out", skip_fetch=True)
        assert run_pipeline(opts) == 0

    assert (tree / "file.txt").read_text(encoding="utf-8") == "patched\n"
    assert (workspace / "hooked.txt").read_text(encoding="utf-8").strip() == "hooked"


@requires_git
def test_cli_fetch_command_native_sync(tmp_path: Path, monkeypatch) -> None:
    """`cru fetch` drives the native syncer against a local manifest."""
    base = tmp_path
    _make_repo(base / "proj", content="p")
    manifest_git = _make_manifest_repo(
        base,
        """<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <default remote="origin"/>
  <project path="proj" name="proj"/>
</manifest>
""",
    )
    project = base / "project"
    project.mkdir()
    (project / "rc.json").write_text(
        json.dumps(
            {
                "project_name": "TestROM",
                "rom": {
                    "source": str(manifest_git),
                    "branch": "main",
                    "lunch_prefix": "test",
                    "build_target": "bacon",
                },
                "device": {"codename": "testdev"},
                "options": {"use_ccache": False},
                "output": {"format": ".zip"},
                "input": {"archive": "file:///tmp/unused.tar.gz"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(project)

    assert cli.main(["fetch"]) == 0

    workspace = project / "TestROM"
    assert (workspace / "proj" / "file.txt").read_text(encoding="utf-8") == "p"
    assert (workspace / ".cruine" / "manifests" / "default.xml").is_file()
