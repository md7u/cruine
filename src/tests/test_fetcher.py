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


@requires_git
def test_fetch_clones_pinned_revision(tmp_path: Path) -> None:
    """repository.revision pins a device tree to a tag/branch via --branch."""
    base = tmp_path
    device_git = _make_repo(base / "device-tree", content="v1")
    _git("tag", "v1.0", cwd=device_git)
    (device_git / "file.txt").write_text("v2", encoding="utf-8")
    _git("add", ".", cwd=device_git)
    _git("commit", "-m", "second", cwd=device_git)
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
            {
                "type": "device",
                "url": str(device_git),
                "target_path": "device/test/testdev",
                "revision": "v1.0",
            }
        ],
    )
    workspace = base / "ws"
    SourceFetcher(recipe, workspace, jobs=1).fetch()

    cloned = workspace / "device" / "test" / "testdev"
    assert (cloned / ".git").exists()
    assert (cloned / "file.txt").read_text(encoding="utf-8") == "v1"


def test_run_retry_cleans_partial_clone_between_attempts(tmp_path: Path, monkeypatch) -> None:
    """A failed clone attempt removes its partial destination before retrying."""
    monkeypatch.setattr(SourceFetcher, "RETRY_DELAY_SECONDS", 0)
    (tmp_path / "ws").mkdir()
    fetcher = SourceFetcher(_recipe("https://example.com/android.git"), tmp_path / "ws")
    dest = tmp_path / "dest"
    marker = tmp_path / "attempt-marker"
    script = (
        f"if [ ! -f {marker} ]; then touch {marker}; mkdir -p {dest}; exit 1; fi; "
        f"if [ -d {dest} ]; then exit 2; fi; mkdir -p {dest}; exit 0"
    )

    fetcher._run_retry(["bash", "-c", script], "clone test", retry_cleanup_path=dest)

    assert marker.is_file()
    assert dest.is_dir()


def test_run_retry_keeps_pre_existing_destination(tmp_path: Path, monkeypatch) -> None:
    """A destination owned by the caller is never removed between retries."""
    monkeypatch.setattr(SourceFetcher, "RETRY_DELAY_SECONDS", 0)
    (tmp_path / "ws").mkdir()
    fetcher = SourceFetcher(_recipe("https://example.com/android.git"), tmp_path / "ws")
    dest = tmp_path / "owned"
    dest.mkdir()
    (dest / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(FetchError):
        fetcher._run_retry(
            ["bash", "-c", "exit 1"],
            "clone test",
            retry_cleanup_path=dest,
        )

    assert (dest / "keep.txt").is_file()
