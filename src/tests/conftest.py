"""Shared fixtures for the cruine test suite."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

SAMPLE_RECIPE: dict = {
    "project_name": "TestROM",
    "rom": {
        "source": "https://example.com/android.git",
        "branch": "test-branch",
        "lunch_prefix": "test",
        "build_target": "bacon",
    },
    "device": {
        "codename": "testdevice",
        "repositories": [
            {
                "type": "device",
                "url": "https://example.com/device.git",
                "target_path": "device/test/testdevice",
            }
        ],
    },
    "options": {"use_ccache": False},
    "output": {"format": ".zip"},
}


@pytest.fixture
def sample_recipe() -> dict:
    return json.loads(json.dumps(SAMPLE_RECIPE))


@pytest.fixture
def recipe_file(tmp_path: Path, sample_recipe: dict) -> Path:
    path = tmp_path / "rc.json"
    path.write_text(json.dumps(sample_recipe), encoding="utf-8")
    return path


@pytest.fixture(autouse=True, scope="session")
def _hermetic_config(tmp_path_factory: pytest.TempPathFactory):
    """Point CRUINE_CONFIG at a non-existent file so a developer's real
    ~/.config/cruine/config.toml never leaks into the test run."""
    previous = os.environ.get("CRUINE_CONFIG")
    os.environ["CRUINE_CONFIG"] = str(tmp_path_factory.mktemp("cruine-config") / "config.toml")
    yield
    if previous is None:
        os.environ.pop("CRUINE_CONFIG", None)
    else:
        os.environ["CRUINE_CONFIG"] = previous


@pytest.fixture(autouse=True, scope="session")
def _jdk_shims(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Guarantee a resolvable JDK for env validation without a system install.

    AOSP builds require ``java`` + ``javac`` on PATH, so the pipeline and
    ``doctor`` gate on them. On hosts without a real JDK this fixture drops
    tiny stubs into PATH that only satisfy the version probe (``java -version``)
    so the test suite stays hermetic. Real JDKs are never shadowed.
    """
    if shutil.which("java") and shutil.which("javac"):
        return
    bin_dir = tmp_path_factory.mktemp("jdk-shims")
    java = bin_dir / "java"
    javac = bin_dir / "javac"
    java.write_text(
        "#!/bin/sh\necho 'openjdk version \"17.0.9\" 2026-01-01' 1>&2\nexit 0\n",
        encoding="utf-8",
    )
    javac.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    java.chmod(0o755)
    javac.chmod(0o755)
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"
