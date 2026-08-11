"""Tests for SourceFetcher: native manifest sync plus device tree acquisition."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from cruine.core.fetcher import FetchError, SourceFetcher
from cruine.models.recipe import RecipeSchema

GIT = shutil.which("git")
requires_git = pytest.mark.skipif(GIT is None, reason="git not available")


def _git(*args: str, cwd: Path) -> None:
    subprocess.run([GIT, *args], cwd=cwd, check=True, capture_output=True)


def _make_repo(path: Path, branch: str = "main", content: str = "hello") -> Path:
    path.mkdir(parents=True)
    _git("init", "-b", branch, cwd=path)
    _git("config", "user.email", "test@cruine.dev", cwd=path)
    _git("config", "user.name", "Cruine Test", cwd=path)
    (path / "file.txt").write_text(content, encoding="utf-8")
    _git("add", ".", cwd=path)
    _git("commit", "-m", "initial", cwd=path)
    return path


def _make_manifest(base: Path, body: str) -> Path:
    repo = _make_repo(base / "manifests")
    (repo / "default.xml").write_text(body, encoding="utf-8")
    _git("add", ".", cwd=repo)
    _git("commit", "-m", "manifest", cwd=repo)
    return repo


def _recipe(source: str, **device: object) -> RecipeSchema:
    data: dict = {
        "project_name": "TestROM",
        "rom": {
            "source": source,
            "branch": "main",
            "lunch_prefix": "test",
            "build_target": "bacon",
        },
        "device": {"codename": "testdev", **device},
        "options": {"use_ccache": False},
        "output": {"format": ".zip"},
        "input": {"archive": "file:///tmp/unused.tar.gz"},
    }
    return RecipeSchema.model_validate(data)


@requires_git
def test_fetch_syncs_manifest_and_device_trees(tmp_path: Path) -> None:
    base = tmp_path
    _make_repo(base / "proj-a", content="a")
    device_git = _make_repo(base / "device-tree", content="device")
    manifest_git = _make_manifest(
        base,
        """<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <default remote="origin"/>
  <project path="proj-a" name="proj-a"/>
</manifest>
""",
    )

    recipe = _recipe(
        str(manifest_git),
        repositories=[
            {"type": "device", "url": str(device_git), "target_path": "device/test/testdev"}
        ],
    )
    workspace = tmp_path / "ws"
    SourceFetcher(recipe, workspace, jobs=1).fetch()

    assert (workspace / "proj-a" / "file.txt").read_text(encoding="utf-8") == "a"
    assert (workspace / "device" / "test" / "testdev" / ".git").exists()
    assert (workspace / "device" / "test" / "testdev" / "file.txt").read_text(
        encoding="utf-8"
    ) == "device"
    assert (workspace / ".cruine" / "manifests" / "default.xml").is_file()


@requires_git
def test_fetch_copies_local_files(tmp_path: Path) -> None:
    base = tmp_path
    manifest_git = _make_manifest(
        base,
        """<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <default remote="origin"/>
</manifest>
""",
    )
    local_source = base / "local-tree"
    local_source.mkdir()
    (local_source / "props.prop").write_text("ro.test=1\n", encoding="utf-8")

    recipe = _recipe(
        str(manifest_git),
        files=[{"type": "device", "url": str(local_source), "target_path": "device/test/local"}],
    )
    workspace = base / "ws"
    SourceFetcher(recipe, workspace, jobs=1).fetch()

    target = workspace / "device" / "test" / "local"
    assert (target / "props.prop").read_text(encoding="utf-8") == "ro.test=1\n"


@requires_git
def test_fetch_missing_local_file_raises(tmp_path: Path) -> None:
    base = tmp_path
    manifest_git = _make_manifest(
        base,
        """<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <default remote="origin"/>
</manifest>
""",
    )
    recipe = _recipe(
        str(manifest_git),
        files=[{"type": "other", "url": str(base / "nope"), "target_path": "x/y"}],
    )
    with pytest.raises(FetchError):
        SourceFetcher(recipe, base / "ws", jobs=1).fetch()


@requires_git
def test_fetch_respects_repo_dir_not_touched(tmp_path: Path) -> None:
    base = tmp_path
    _make_repo(base / "proj", content="p")
    manifest_git = _make_manifest(
        base,
        """<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <default remote="origin"/>
  <project path="proj" name="proj"/>
</manifest>
""",
    )
    workspace = base / "ws"
    workspace.mkdir()
    legacy = workspace / ".repo"
    legacy.mkdir()
    marker = legacy / "marker"
    marker.write_text("legacy", encoding="utf-8")

    SourceFetcher(_recipe(str(manifest_git)), workspace, jobs=1).fetch()

    assert marker.read_text(encoding="utf-8") == "legacy"
    assert (workspace / "proj" / "file.txt").read_text(encoding="utf-8") == "p"


@requires_git
def test_fetch_removes_stale_partial_clone_dir(tmp_path: Path) -> None:
    base = tmp_path
    device_git = _make_repo(base / "device-tree", content="device")
    manifest_git = _make_manifest(
        base,
        """<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <default remote="origin"/>
</manifest>
""",
    )
    recipe = _recipe(
        str(manifest_git),
        repositories=[
            {"type": "device", "url": str(device_git), "target_path": "device/test/testdev"}
        ],
    )
    workspace = base / "ws"
    stale = workspace / "device" / "test" / "testdev"
    stale.mkdir(parents=True)
    (stale / "partial-file").write_text("junk", encoding="utf-8")

    SourceFetcher(recipe, workspace, jobs=1).fetch()

    assert (stale / ".git").exists()
    assert (stale / "file.txt").read_text(encoding="utf-8") == "device"
    assert not (stale / "partial-file").exists()
