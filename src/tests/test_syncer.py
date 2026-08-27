"""Tests for the native manifest sync engine (syncer.py).

These tests build real local git repositories and a small AOSP-style
manifest, then verify that ManifestSyncer clones, updates, and skips
unchanged projects exactly like the ``repo`` tool would.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from cruine.core.syncer import (
    ManifestParser,
    ManifestSyncer,
    SyncError,
    active_projects,
    is_absolute_ref,
    ref_name,
)
from cruine.models.recipe import RecipeSchema

GIT = shutil.which("git")
requires_git = pytest.mark.skipif(GIT is None, reason="git not available")


def _git(*args: str, cwd: Path) -> None:
    subprocess.run([GIT, *args], cwd=cwd, check=True, capture_output=True)


def _commit(repo: Path, message: str, content: str = "hello") -> None:
    (repo / "file.txt").write_text(content, encoding="utf-8")
    _git("add", ".", cwd=repo)
    _git("commit", "-m", message, cwd=repo)


def _make_repo(path: Path, branch: str = "main", content: str = "hello") -> Path:
    path.mkdir(parents=True)
    _git("init", "-b", branch, cwd=path)
    _git("config", "user.email", "test@cruine.dev", cwd=path)
    _git("config", "user.name", "Cruine Test", cwd=path)
    _commit(path, "initial", content)
    return path


def _write_manifest(base: Path, body: str) -> Path:
    repo = _make_repo(base / "manifests")
    (repo / "default.xml").write_text(body, encoding="utf-8")
    _git("add", ".", cwd=repo)
    _git("commit", "-m", "manifest", cwd=repo)
    return repo


def _recipe(source: str, branch: str = "main", **extra: object) -> RecipeSchema:
    data: dict = {
        "project_name": "TestROM",
        "rom": {
            "source": source,
            "branch": branch,
            "lunch_prefix": "test",
            "build_target": "bacon",
        },
        "device": {"codename": "testdevice"},
        "options": {"use_ccache": False},
        "output": {"format": ".zip"},
        "input": {"archive": "file:///tmp/unused.tar.gz"},
    }
    data["rom"].update(extra)
    return RecipeSchema.from_dict(data)


def _sample_manifest() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <default remote="origin"/>
  <project path="device/x" name="device-x" revision="main"/>
  <project path="vendor/y" name="vendor-y" groups="pdk,notdefault"/>
</manifest>
"""


@requires_git
def test_parser_roundtrip(tmp_path: Path) -> None:
    parser = ManifestParser(tmp_path)
    parsed = parser.parse(_sample_manifest())
    assert parsed.default_remote == "origin"
    assert len(parsed.projects) == 2
    assert parsed.projects[0].path == "device/x"
    assert parsed.remotes["origin"].fetch == "."
    active = active_projects(parsed)
    assert [p.path for p in active] == ["device/x"]  # pdk excluded from default


@requires_git
def test_parser_strips_bom(tmp_path: Path) -> None:
    parser = ManifestParser(tmp_path)
    parsed = parser.parse("\ufeff" + _sample_manifest())
    assert parsed.default_remote == "origin"
    assert len(parsed.projects) == 2


@requires_git
def test_ref_and_sha_helpers() -> None:
    assert ref_name("refs/heads/main") == "main"
    assert ref_name("refs/tags/v1.0") == "v1.0"
    assert ref_name("main") == "main"
    assert is_absolute_ref("a" * 40)
    assert not is_absolute_ref("main")


@requires_git
def test_sync_clones_and_skips(tmp_path: Path) -> None:
    base = tmp_path
    device_repo = _make_repo(base / "device-x", content="device")
    vendor_repo = _make_repo(base / "vendor-y", content="vendor")
    _write_manifest(base, _sample_manifest())
    assert device_repo.exists() and vendor_repo.exists()

    workspace = tmp_path / "ws"
    recipe = _recipe(str(base / "manifests"))
    syncer = ManifestSyncer(recipe, workspace, jobs=1)

    count = syncer.sync()
    assert count == 1  # only the default group project

    project_dir = workspace / "device" / "x"
    assert (project_dir / "file.txt").read_text(encoding="utf-8") == "device"
    assert (workspace / ".cruine" / "manifests" / "default.xml").is_file()
    assert (workspace / ".cruine" / "state.json").is_file()

    # The fresh syncer recognises the project as unchanged and skips it.
    syncer2 = ManifestSyncer(recipe, workspace, jobs=1)
    assert syncer2._unchanged(project_dir, str(base / "device-x"), "main") is True


@requires_git
def test_sync_picks_up_new_commit(tmp_path: Path) -> None:
    base = tmp_path
    device_repo = _make_repo(base / "device-x", content="v1")
    _write_manifest(base, _sample_manifest())

    workspace = tmp_path / "ws"
    recipe = _recipe(str(base / "manifests"))
    ManifestSyncer(recipe, workspace, jobs=1).sync()

    _commit(device_repo, "v2", "v2-content")
    ManifestSyncer(recipe, workspace, jobs=1).sync()
    updated = workspace / "device" / "x" / "file.txt"
    assert updated.read_text(encoding="utf-8") == "v2-content"


@requires_git
def test_groups_filtering_and_remove_project(tmp_path: Path) -> None:
    base = tmp_path
    _make_repo(base / "device-x", content="device")
    _make_repo(base / "vendor-y", content="vendor")
    manifest = """<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <default remote="origin"/>
  <project path="device/x" name="device-x"/>
  <project path="vendor/y" name="vendor-y" groups="pdk,notdefault"/>
  <remove-project name="device-x"/>
</manifest>
"""
    _write_manifest(base, manifest)

    recipe = _recipe(str(base / "manifests"), groups="pdk")
    workspace = tmp_path / "ws"
    ManifestSyncer(recipe, workspace, jobs=1).sync()

    assert (workspace / "device" / "x").exists() is False
    assert (workspace / "vendor" / "y" / "file.txt").exists()
    assert (workspace / "vendor" / "y" / "file.txt").read_text(encoding="utf-8") == "vendor"


@requires_git
def test_copyfile_and_linkfile(tmp_path: Path) -> None:
    base = tmp_path
    project_repo = _make_repo(base / "proj", content="proj")
    (project_repo / "build.env").write_text("SOURCE=yes", encoding="utf-8")
    _git("add", ".", cwd=project_repo)
    _git("commit", "-m", "add env", cwd=project_repo)

    manifest = """<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <default remote="origin"/>
  <project path="proj" name="proj">
    <copyfile src="build.env" dest="copy.env"/>
    <linkfile src="build.env" dest="link.env"/>
  </project>
</manifest>
"""
    _write_manifest(base, manifest)

    workspace = tmp_path / "ws"
    ManifestSyncer(_recipe(str(base / "manifests")), workspace, jobs=1).sync()

    assert (workspace / "proj" / "copy.env").read_text(encoding="utf-8") == "SOURCE=yes"
    assert (workspace / "proj" / "link.env").is_symlink()
    assert (workspace / "proj" / "link.env").read_text(encoding="utf-8") == "SOURCE=yes"


@requires_git
def test_sha_revision_syncs_detached(tmp_path: Path) -> None:
    base = tmp_path
    repo = _make_repo(base / "proj", content="one")
    sha = subprocess.run(
        [GIT, "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()

    manifest = f"""<manifest>
  <remote name="origin" fetch="."/>
  <default remote="origin" revision="{sha}"/>
  <project path="proj" name="proj"/>
</manifest>
"""
    _write_manifest(base, manifest)

    workspace = tmp_path / "ws"
    syncer = ManifestSyncer(_recipe(str(base / "manifests")), workspace, jobs=1)
    syncer.sync()

    head = subprocess.run(
        [GIT, "rev-parse", "HEAD"],
        cwd=workspace / "proj",
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head == sha


@requires_git
def test_branch_ref_prefix_revision(tmp_path: Path) -> None:
    base = tmp_path
    _make_repo(base / "proj", branch="main")
    manifest = """<manifest>
  <remote name="origin" fetch="." revision="refs/heads/main"/>
  <default remote="origin"/>
  <project path="proj" name="proj"/>
</manifest>
"""
    _write_manifest(base, manifest)

    workspace = tmp_path / "ws"
    ManifestSyncer(_recipe(str(base / "manifests")), workspace, jobs=1).sync()
    assert (workspace / "proj" / "file.txt").is_file()


@requires_git
def test_local_manifest_merge(tmp_path: Path) -> None:
    base = tmp_path
    _make_repo(base / "proj-a", content="a")
    _make_repo(base / "proj-b", content="b")
    _write_manifest(
        base,
        """<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <default remote="origin"/>
  <project path="proj-a" name="proj-a"/>
</manifest>
""",
    )

    workspace = tmp_path / "ws"
    local_dir = workspace / ".cruine" / "local_manifests"
    local_dir.mkdir(parents=True)
    (local_dir / "extra.xml").write_text(
        """<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <project path="proj-b" name="proj-b"/>
</manifest>
""",
        encoding="utf-8",
    )

    ManifestSyncer(_recipe(str(base / "manifests")), workspace, jobs=1).sync()
    assert (workspace / "proj-a" / "file.txt").exists()
    assert (workspace / "proj-b" / "file.txt").exists()


@requires_git
def test_extend_project_and_include(tmp_path: Path) -> None:
    base = tmp_path
    _make_repo(base / "proj", content="orig")
    _write_manifest(
        base,
        """<manifest>
  <remote name="origin" fetch="."/>
  <default remote="origin"/>
  <include name="extras.xml"/>
</manifest>
""",
    )
    # extras.xml lives inside the manifest repo
    manifest_repo = base / "manifests"
    (manifest_repo / "extras.xml").write_text(
        "<manifest>\n"
        '  <project path="proj" name="proj" revision="main"/>\n'
        '  <extend-project name="proj" remote="origin"/>\n'
        "</manifest>\n",
        encoding="utf-8",
    )
    _git("add", ".", cwd=manifest_repo)
    _git("commit", "-m", "add extras", cwd=manifest_repo)

    workspace = tmp_path / "ws"
    ManifestSyncer(_recipe(str(base / "manifests")), workspace, jobs=1).sync()
    assert (workspace / "proj" / "file.txt").read_text(encoding="utf-8") == "orig"


@requires_git
def test_remote_alias(tmp_path: Path) -> None:
    base = tmp_path / "src"
    _make_repo(base / "proj", content="aliased")
    manifest = """<manifest>
  <remote name="primary" alias="p" fetch="." revision="main"/>
  <default remote="p"/>
  <project path="proj" name="proj"/>
</manifest>
"""
    _write_manifest(base, manifest)
    workspace = tmp_path / "ws"
    ManifestSyncer(_recipe(str(base / "manifests")), workspace, jobs=1).sync()
    assert (workspace / "proj" / "file.txt").read_text(encoding="utf-8") == "aliased"


@requires_git
def test_shallow_clone_passes_depth(tmp_path: Path, monkeypatch) -> None:
    """--depth is passed to git clone (real remotes get shallow clones).

    Note: git deliberately ignores --depth when cloning from a plain local
    path (it uses hardlinks instead), so this asserts the flag is propagated
    to the clone command rather than checking for a .git/shallow marker.
    """
    base = tmp_path / "src"
    _make_repo(base / "proj", content="shallow")
    _write_manifest(base, _proj_manifest())
    workspace = tmp_path / "ws"

    clone_commands: list[list[str]] = []

    def _spy_retry(command: list[str], label: str, **kwargs: object) -> None:
        if command[1] == "clone":
            clone_commands.append(command)
        return original_retry(command, label, **kwargs)

    import cruine.core.syncer as module

    original_retry = module.run_retry
    monkeypatch.setattr(module, "run_retry", _spy_retry)
    recipe = _recipe(str(base / "manifests"), depth=1)
    ManifestSyncer(recipe, workspace, jobs=1).sync()

    project_clones = [c for c in clone_commands if str(workspace / "proj") in c]
    assert len(project_clones) == 1
    assert "--depth" in project_clones[0]
    assert "1" in project_clones[0]


@requires_git
def test_clone_depth_attribute_from_manifest(tmp_path: Path, monkeypatch) -> None:
    """AOSP manifests use clone-depth=\"N\"; the parser must honour it."""
    base = tmp_path / "src"
    _make_repo(base / "proj", content="shallow")
    manifest = """<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <default remote="origin"/>
  <project path="proj" name="proj" clone-depth="1"/>
</manifest>
"""
    _write_manifest(base, manifest)
    workspace = tmp_path / "ws"

    clone_commands: list[list[str]] = []

    import cruine.core.syncer as module

    def _spy_retry(command: list[str], label: str, **kwargs: object) -> None:
        if command[1] == "clone":
            clone_commands.append(command)
        return original_retry(command, label, **kwargs)

    original_retry = module.run_retry
    monkeypatch.setattr(module, "run_retry", _spy_retry)
    ManifestSyncer(_recipe(str(base / "manifests")), workspace, jobs=1).sync()

    project_clones = [c for c in clone_commands if str(workspace / "proj") in c]
    assert len(project_clones) == 1
    assert "--depth" in project_clones[0]
    assert "1" in project_clones[0]


@requires_git
def test_tag_revision_syncs_detached(tmp_path: Path) -> None:
    base = tmp_path / "src"
    repo = _make_repo(base / "proj", content="v1")
    _git("tag", "v1.0", cwd=repo)
    _commit(repo, "v2", "v2-content")

    manifest = """<manifest>
  <remote name="origin" fetch="."/>
  <default remote="origin" revision="v1.0"/>
  <project path="proj" name="proj"/>
</manifest>
"""
    _write_manifest(base, manifest)
    workspace = tmp_path / "ws"
    ManifestSyncer(_recipe(str(base / "manifests")), workspace, jobs=1).sync()
    assert (workspace / "proj" / "file.txt").read_text(encoding="utf-8") == "v1"


@requires_git
def test_parallel_jobs_sync_all(tmp_path: Path) -> None:
    base = tmp_path / "src"
    for i in range(6):
        _make_repo(base / f"proj-{i}", content=f"p{i}")
    projects = "\n".join(f'  <project path="proj-{i}" name="proj-{i}"/>' for i in range(6))
    _write_manifest(
        base,
        '<manifest>\n  <remote name="origin" fetch="." revision="main"/>\n'
        f'  <default remote="origin"/>\n{projects}\n</manifest>\n',
    )
    workspace = tmp_path / "ws"
    count = ManifestSyncer(_recipe(str(base / "manifests")), workspace, jobs=4).sync()
    assert count == 6
    for i in range(6):
        assert (workspace / f"proj-{i}" / "file.txt").read_text(encoding="utf-8") == f"p{i}"


@requires_git
def test_submanifest_prefixes_project_paths(tmp_path: Path) -> None:
    base = tmp_path / "src"
    _make_repo(base / "proj-c", content="c")
    _write_manifest(
        base,
        """<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <default remote="origin"/>
  <submanifest path="vendor/g">
    <project path="proj-c" name="proj-c"/>
  </submanifest>
</manifest>
""",
    )
    workspace = tmp_path / "ws"
    ManifestSyncer(_recipe(str(base / "manifests")), workspace, jobs=1).sync()
    assert (workspace / "vendor" / "g" / "proj-c" / "file.txt").read_text(encoding="utf-8") == "c"


def _proj_manifest() -> str:
    return """<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <default remote="origin"/>
  <project path="proj" name="proj"/>
</manifest>
"""


@requires_git
def test_missing_manifest_file_raises(tmp_path: Path) -> None:
    base = tmp_path
    _make_repo(base / "manifests")
    workspace = tmp_path / "ws"
    syncer = ManifestSyncer(_recipe(str(base / "manifests")), workspace, jobs=1)
    with pytest.raises(SyncError):
        syncer.sync()


@requires_git
def test_unsafe_project_path_rejected(tmp_path: Path) -> None:
    base = tmp_path
    _make_repo(base / "proj")
    manifest = """<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <default remote="origin"/>
  <project path="../../evil" name="proj"/>
</manifest>
"""
    _write_manifest(base, manifest)
    workspace = tmp_path / "ws"
    syncer = ManifestSyncer(_recipe(str(base / "manifests")), workspace, jobs=1)
    with pytest.raises(SyncError):
        syncer.sync()


@requires_git
def test_dry_state_file(tmp_path: Path) -> None:
    """state.json round-trips through a fresh syncer without re-fetching."""
    base = tmp_path
    _make_repo(base / "proj")
    _write_manifest(
        base,
        """<manifest>
  <remote name="origin" fetch="." revision="main"/>
  <default remote="origin"/>
  <project path="proj" name="proj"/>
</manifest>
""",
    )
    workspace = tmp_path / "ws"
    ManifestSyncer(_recipe(str(base / "manifests")), workspace, jobs=1).sync()

    state = json.loads((workspace / ".cruine" / "state.json").read_text(encoding="utf-8"))
    assert any("proj" in key for key in state)
