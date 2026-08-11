"""Tests for the environment manager."""

from __future__ import annotations

import subprocess
from pathlib import Path

from cruine.core.environment import (
    REQUIRED_TOOLS,
    EnvironmentManager,
)
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


def test_check_tools_no_overlap() -> None:
    report = EnvironmentManager().check_tools()
    assert set(report.present).isdisjoint(report.missing)


def test_check_tools_finds_bash() -> None:
    report = EnvironmentManager().check_tools()
    assert "bash" in report.present


def test_inspect_host_fields() -> None:
    report = EnvironmentManager().inspect_host()
    assert report.cpu_cores >= 1
    assert report.recommended_jobs >= 1
    assert isinstance(report.python_version, str)
    assert set(report.missing_required).issubset(report.tools.missing)
    assert set(report.missing_build_tools).issubset(report.tools.missing)
    assert set(report.missing_optional).issubset(report.tools.missing)
    assert not set(report.missing_required) & set(report.missing_optional)
    assert not set(report.missing_required) & set(report.missing_build_tools)


def test_required_tools_include_jdk() -> None:
    assert "java" in REQUIRED_TOOLS
    assert "javac" in REQUIRED_TOOLS


def test_host_build_tools_include_both_compiler_sets() -> None:
    from cruine.core.environment import HOST_BUILD_TOOLS

    assert "clang" in HOST_BUILD_TOOLS
    assert "clang++" in HOST_BUILD_TOOLS
    assert "gcc" in HOST_BUILD_TOOLS
    assert "g++" in HOST_BUILD_TOOLS


def test_libc_detection_returns_known_value(monkeypatch) -> None:
    monkeypatch.delenv("CRUINE_LIBC", raising=False)
    assert EnvironmentManager.detect_libc() in ("musl", "glibc")


def test_libc_detection_override(monkeypatch) -> None:
    monkeypatch.setenv("CRUINE_LIBC", "musl")
    assert EnvironmentManager.detect_libc() == "musl"
    monkeypatch.setenv("CRUINE_LIBC", "glibc")
    assert EnvironmentManager.detect_libc() == "glibc"


def test_toolchain_for_libc() -> None:
    assert EnvironmentManager.toolchain_for("musl") == ("clang", "clang++")
    assert EnvironmentManager.toolchain_for("glibc") == ("gcc", "g++")


def test_target_triple_for() -> None:
    assert EnvironmentManager.target_triple_for("musl", "amd64") == "x86_64-unknown-linux-musl"
    assert EnvironmentManager.target_triple_for("musl", "arm64") == "aarch64-unknown-linux-musl"
    assert EnvironmentManager.target_triple_for("glibc", "amd64") == "x86_64-unknown-linux-gnu"
    assert EnvironmentManager.target_triple_for("glibc", "arm64") == "aarch64-unknown-linux-gnu"


def test_inspect_host_reports_profile(monkeypatch) -> None:
    monkeypatch.setenv("CRUINE_LIBC", "musl")
    report = EnvironmentManager().inspect_host()
    assert report.libc == "musl"
    assert report.cc == "clang"
    assert report.cxx == "clang++"
    assert report.arch in ("amd64", "arm64")
    assert report.target_triple.startswith(("x86_64-", "aarch64-"))
    assert report.target_triple.endswith("-unknown-linux-musl")


def test_java_version_parsing(tmp_path: Path) -> None:
    def script(output: str) -> str:
        path = tmp_path / f"java-{abs(hash(output))}"
        path.write_text(
            f"#!/bin/sh\necho '{output}' 1>&2\nexit 0\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return str(path)

    assert EnvironmentManager._java_version(script('openjdk version "17.0.9"')) == (
        "17.0.9",
        17,
    )
    assert EnvironmentManager._java_version(script('java version "1.8.0_292"')) == (
        "1.8.0_292",
        8,
    )
    assert EnvironmentManager._java_version(script('openjdk version "11.0.22"')) == (
        "11.0.22",
        11,
    )
    assert EnvironmentManager._java_version(script("garbage")) == (None, None)


def test_java_report_aosp_hints() -> None:
    assert EnvironmentManager().check_java().is_jdk
    from cruine.core.environment import JavaReport

    assert JavaReport(None, None, None, 17).aosp_hint is not None
    assert JavaReport(None, None, None, 11).aosp_hint is not None
    assert JavaReport(None, None, None, 8).aosp_hint is not None
    assert JavaReport(None, None, None, 23).aosp_hint is not None
    assert JavaReport(None, None, None, None).aosp_hint is None
    assert JavaReport(None, "/usr/bin/javac", "17", 17).is_jdk is True
    assert JavaReport("/usr/bin/java", None, "17", 17).is_jdk is False


def test_build_environment_sets_env(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CCACHE_DIR", str(tmp_path / "cc"))
    recipe = _recipe()
    recipe.options.use_ccache = True
    env = EnvironmentManager().build_environment(recipe, 4)
    assert env["USE_CCACHE"] == "1"
    assert env["CRU_JOBS"] == "4"
    assert env["LC_ALL"] == "C"
    assert env["CCACHE_DIR"] == str(tmp_path / "cc")


def test_build_environment_disables_ccache(monkeypatch) -> None:
    monkeypatch.delenv("CCACHE_DIR", raising=False)
    env = EnvironmentManager().build_environment(_recipe(), 2)
    assert "USE_CCACHE" not in env


def test_check_disk_space(tmp_path) -> None:
    ok, free_gb = EnvironmentManager().check_disk_space(tmp_path, 0.0)
    assert ok is True
    assert free_gb >= 0


def test_setup_ccache_passes_ccache_dir_env(monkeypatch, tmp_path) -> None:
    import shutil

    ccache_dir = tmp_path / "ccache"
    calls: list[dict] = []
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: "/usr/bin/ccache" if name == "ccache" else None,
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: calls.append(kwargs) or subprocess.CompletedProcess(args[0], 0),
    )
    recipe = _recipe()
    recipe.options.use_ccache = True
    manager = EnvironmentManager()
    manager.ccache_dir = ccache_dir
    manager.setup_ccache(recipe)
    assert calls
    assert calls[0]["env"]["CCACHE_DIR"] == str(ccache_dir)
