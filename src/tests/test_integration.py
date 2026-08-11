"""End-to-end pipeline test: rc.json discovery -> fetch -> build -> package -> export.

Runs the real `cru <destination>` code path (cli.main) against a synthetic
but fully functional workspace: a real local git repository is cloned, a real
bash build is executed against fake envsetup/lunch/mka shims, and the real
packager produces a .zip archive in the destination directory.

Requires git, bash, tar on PATH (the standard host prerequisites).
"""

from __future__ import annotations

import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

GIT_TOOLS_AVAILABLE = pytest.mark.skipif(
    not (Path("/usr/bin/git").exists() or Path("/usr/bin/bash").exists()),
    reason="git/bash not available on this host",
)


def _write_shim(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _make_bare_repo(root: Path, name: str) -> Path:
    work = root / f"{name}-work"
    work.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(work)], check=True, capture_output=True)
    (work / "vendor.txt").write_text("device tree source\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "vendor.txt"],
        cwd=str(work),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            "initial",
        ],
        cwd=str(work),
        check=True,
        capture_output=True,
    )
    bare = root / f"{name}.git"
    subprocess.run(
        ["git", "clone", "--bare", str(work), str(bare)], check=True, capture_output=True
    )
    return bare


def _make_manifest_repo(root: Path) -> Path:
    work = root / "manifest-work"
    work.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(work)], check=True, capture_output=True)
    (work / "default.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<manifest>\n"
        '  <remote name="origin" fetch="." revision="main"/>\n'
        '  <default remote="origin"/>\n'
        "</manifest>\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "default.xml"],
        cwd=str(work),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            "manifest",
        ],
        cwd=str(work),
        check=True,
        capture_output=True,
    )
    repo = root / "manifest.git"
    subprocess.run(
        ["git", "clone", "--bare", str(work), str(repo)], check=True, capture_output=True
    )
    return repo


@GIT_TOOLS_AVAILABLE
def test_full_pipeline_cru_destination(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)

    device_git = _make_bare_repo(tmp_path, "device")
    manifest_git = _make_manifest_repo(tmp_path)

    recipe = {
        "project_name": "TestROM",
        "rom": {
            "source": str(manifest_git),
            "branch": "main",
            "lunch_prefix": "test",
            "build_target": "bacon",
        },
        "device": {
            "codename": "testdev",
            "repositories": [
                {"type": "device", "url": str(device_git), "target_path": "device/test/testdev"}
            ],
        },
        "options": {"use_ccache": False, "clean_build": True},
        "output": {"format": ".zip", "compression_level": 6},
    }
    (project / "rc.json").write_text(json.dumps(recipe), encoding="utf-8")

    tools = tmp_path / "tools"
    tools.mkdir()
    _write_shim(tools / "lunch", "#!/bin/sh\n# fake lunch\nexit 0\n")
    _write_shim(
        tools / "mka",
        "#!/bin/sh\n"
        'mkdir -p "$PWD/out/target/product/testdev"\n'
        'echo fake-system > "$PWD/out/target/product/testdev/system.img"\n'
        'echo fake-boot > "$PWD/out/target/product/testdev/boot.img"\n',
    )
    monkeypatch.setenv("PATH", str(tools) + os.pathsep + os.environ.get("PATH", ""))

    workspace = project / "TestROM"
    (workspace / "build").mkdir(parents=True)
    (workspace / "build" / "envsetup.sh").write_text(
        "#!/bin/bash\n# fake envsetup\nexport FAKE=1\n"
    )

    from cruine.cli import main

    destination = tmp_path / "out"
    assert main(["--verbose", str(destination)]) == 0

    archive = destination / "TestROM-testdev.zip"
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        assert "system.img" in names
        assert "boot.img" in names

    assert (destination / "TestROM-build.log").is_file()
    assert (workspace / ".cruine" / "manifests" / "default.xml").is_file()
    assert (workspace / "device" / "test" / "testdev" / ".git").exists()
    assert (workspace / "device" / "test" / "testdev" / "vendor.txt").is_file()
