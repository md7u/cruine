"""Tests for the archive packager."""

from __future__ import annotations

import shutil
import tarfile
import zipfile
from pathlib import Path

import pytest
from cruine.core.packager import OutputPackager, PackagingError
from cruine.models.recipe import RecipeSchema

requires_7z = pytest.mark.skipif(shutil.which("7z") is None, reason="7z not available")


def _make_out_dir(tmp_path: Path) -> Path:
    out = tmp_path / "out" / "target" / "product" / "testdevice"
    (out / "system" / "bin").mkdir(parents=True)
    (out / "system" / "bin" / "tool").write_text("x", encoding="utf-8")
    (out / "system" / "obj").mkdir()
    (out / "system" / "obj" / "junk").write_text("y", encoding="utf-8")
    (out / "boot.img").write_text("boot", encoding="utf-8")
    (out / "system.img").write_text("system", encoding="utf-8")
    return out


def _recipe(fmt: str = ".zip") -> RecipeSchema:
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
        output={"format": fmt},
    )


def test_package_zip(tmp_path: Path) -> None:
    _make_out_dir(tmp_path)
    packager = OutputPackager(_recipe(), tmp_path, tmp_path / "dest")
    target = packager.package()
    assert target.name == "TestROM-testdevice.zip"
    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
        assert "boot.img" in names
        assert "system/bin/tool" in names
        assert not any("obj/" in name for name in names)


def test_package_targz(tmp_path: Path) -> None:
    _make_out_dir(tmp_path)
    packager = OutputPackager(_recipe(".tar.gz"), tmp_path, tmp_path / "dest")
    target = packager.package()
    assert target.name == "TestROM-testdevice.tar.gz"
    with tarfile.open(target) as tf:
        members = {m.name for m in tf.getmembers()}
        assert "boot.img" in members
        assert "system/bin/tool" in members
        assert not any(name.startswith("system/obj") for name in members)


def test_package_tarbz2(tmp_path: Path) -> None:
    _make_out_dir(tmp_path)
    packager = OutputPackager(_recipe(".tar.bz2"), tmp_path, tmp_path / "dest")
    target = packager.package()
    assert target.name == "TestROM-testdevice.tar.bz2"
    with tarfile.open(target) as tf:
        members = {m.name for m in tf.getmembers()}
        assert "boot.img" in members
        assert "system/bin/tool" in members
        assert not any(name.startswith("system/obj") for name in members)


def test_package_img_copies_primary(tmp_path: Path) -> None:
    _make_out_dir(tmp_path)
    packager = OutputPackager(_recipe(".img"), tmp_path, tmp_path / "dest")
    target = packager.package()
    assert target.read_text(encoding="utf-8") == "system"


def test_package_missing_output_raises(tmp_path: Path) -> None:
    packager = OutputPackager(_recipe(), tmp_path, tmp_path / "dest")
    with pytest.raises(PackagingError):
        packager.package()


def test_human_size() -> None:
    assert OutputPackager._human_size(0) == "0.0 B"
    assert "KB" in OutputPackager._human_size(2048)


def test_7z_cli_passes_excluded_dirs(tmp_path: Path, monkeypatch) -> None:
    import shutil
    import subprocess

    _make_out_dir(tmp_path)
    recipe = _recipe(".7z")
    recipe.output.exclude_dirs = ["system/obj", "cache"]
    packager = OutputPackager(recipe, tmp_path, tmp_path / "dest")
    calls: list[tuple[list[str], dict]] = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/7z" if name == "7z" else None)
    monkeypatch.setattr(subprocess, "run", fake_run)
    product_dir = tmp_path / "out" / "target" / "product" / "testdevice"
    packager._make_7z_cli(product_dir, tmp_path / "dest" / "x.7z", 6)
    command, kwargs = calls[0]
    assert command[:3] == ["/usr/bin/7z", "a", "-t7z"]
    assert "-xr!system/obj" in command
    assert "-xr!cache" in command
    assert command[5] == "*"
    assert command.index("*") < command.index("-xr!cache")
    assert kwargs["cwd"] == str(product_dir)


@requires_7z
def test_package_7z_cli_stores_android_tree_layout(tmp_path: Path) -> None:
    import subprocess

    _make_out_dir(tmp_path)
    recipe = _recipe(".7z")
    recipe.output.exclude_dirs = ["system/obj"]
    packager = OutputPackager(recipe, tmp_path, tmp_path / "dest")
    product_dir = tmp_path / "out" / "target" / "product" / "testdevice"
    target = tmp_path / "dest" / "TestROM-testdevice.7z"
    packager._make_7z_cli(product_dir, target, 6)
    listing = subprocess.run(
        ["7z", "l", str(target)], capture_output=True, text=True, check=True
    ).stdout
    assert "system/bin/tool" in listing
    assert "boot.img" in listing
    assert "/system/" not in listing.replace("\\", "/")
    assert "system/obj" not in listing
    assert "out/" not in listing


def test_package_iso_closes_pycdlib_on_error(tmp_path: Path, monkeypatch) -> None:
    import shutil
    import sys

    _make_out_dir(tmp_path)
    packager = OutputPackager(_recipe(".iso"), tmp_path, tmp_path / "dest")
    instances: list[object] = []

    class FakePyCdlib:
        def __init__(self) -> None:
            self.closed = False
            instances.append(self)

        def new(self, **kwargs) -> None:
            pass

        def add_directory(self, *args, **kwargs) -> None:
            pass

        def add_fp(self, *args, **kwargs) -> None:
            pass

        def write(self, target) -> None:
            raise RuntimeError("write failed")

        def close(self) -> None:
            self.closed = True

    fake_module = type(sys)("fake_pycdlib")
    fake_module.PyCdlib = FakePyCdlib
    monkeypatch.setitem(sys.modules, "pycdlib", fake_module)
    monkeypatch.setattr(shutil, "which", lambda name: None)

    with pytest.raises(PackagingError):
        packager._package_iso(tmp_path / "out", tmp_path / "dest" / "x.iso")
    assert instances and instances[0].closed is True
