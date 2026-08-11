"""Tests for ROM archive extraction."""

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest
from cruine.core.extractor import ExtractionError, RomExtractor, detect_format


def _make_zip(path: Path, names: list[str] | None = None) -> Path:
    entries = names or ["system/bin/tool", "boot.img", "system/app/Foo/Foo.apk"]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in entries:
            zf.writestr(name, f"content:{name}")
    return path


def _make_tar_gz(path: Path) -> Path:
    with tarfile.open(path, "w:gz") as tf:
        for name in ["system/bin/tool", "boot.img"]:
            info = tarfile.TarInfo(name)
            data = f"content:{name}".encode()
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return path


def test_detect_format() -> None:
    assert detect_format(Path("rom.tar.gz")) == ".tar.gz"
    assert detect_format(Path("rom.tar.xz")) == ".tar.xz"
    assert detect_format(Path("rom.tar.bz2")) == ".tar.bz2"
    assert detect_format(Path("rom.tgz")) == ".tgz"
    assert detect_format(Path("rom.zip")) == ".zip"
    assert detect_format(Path("rom.7z")) == ".7z"
    assert detect_format(Path("rom.tar")) == ".tar"


def test_extract_tar_bz2(tmp_path: Path) -> None:
    archive = tmp_path / "rom.tar.bz2"
    with tarfile.open(archive, "w:bz2") as tf:
        info = tarfile.TarInfo("system/bin/tool")
        data = b"content:system/bin/tool"
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))
    dest = tmp_path / "out"
    count = RomExtractor().extract(str(archive), dest)
    assert count == 1
    assert (dest / "system" / "bin" / "tool").read_text(
        encoding="utf-8"
    ) == "content:system/bin/tool"


def test_extract_tar_preserves_permissions(tmp_path: Path) -> None:
    archive = tmp_path / "rom.tar"
    with tarfile.open(archive, "w") as tf:
        info = tarfile.TarInfo("system/bin/exec")
        data = b"#!/bin/sh\n"
        info.size = len(data)
        info.mode = 0o755
        tf.addfile(info, io.BytesIO(data))
    dest = tmp_path / "out"
    RomExtractor().extract(str(archive), dest)
    mode = (dest / "system" / "bin" / "exec").stat().st_mode & 0o777
    assert mode == 0o755


def test_detect_format_unknown_raises() -> None:
    with pytest.raises(ExtractionError):
        detect_format(Path("rom.img"))


def test_extract_zip(tmp_path: Path) -> None:
    archive = _make_zip(tmp_path / "rom.zip")
    dest = tmp_path / "out"
    count = RomExtractor().extract(str(archive), dest)
    assert count == 3
    assert (dest / "system" / "bin" / "tool").read_text(
        encoding="utf-8"
    ) == "content:system/bin/tool"
    assert (dest / "boot.img").read_text(encoding="utf-8") == "content:boot.img"


def test_extract_tar_gz(tmp_path: Path) -> None:
    archive = _make_tar_gz(tmp_path / "rom.tar.gz")
    dest = tmp_path / "out"
    count = RomExtractor().extract(str(archive), dest)
    assert count == 2
    assert (dest / "system" / "bin" / "tool").read_text(
        encoding="utf-8"
    ) == "content:system/bin/tool"


def test_extract_missing_archive_raises(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError):
        RomExtractor().extract(str(tmp_path / "nope.zip"), tmp_path / "out")


def test_zip_path_traversal_rejected(tmp_path: Path) -> None:
    archive = _make_zip(tmp_path / "evil.zip", ["../../evil.txt"])
    with pytest.raises(ExtractionError):
        RomExtractor().extract(str(archive), tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


def test_zip_absolute_member_rejected(tmp_path: Path) -> None:
    with zipfile.ZipFile(tmp_path / "abs.zip", "w") as zf:
        zf.writestr("/etc/evil", "x")
    with pytest.raises(ExtractionError):
        RomExtractor().extract(str(tmp_path / "abs.zip"), tmp_path / "out")


def test_7z_cli_rejects_traversal(tmp_path: Path, monkeypatch) -> None:
    import shutil
    import subprocess

    archive = tmp_path / "evil.7z"
    archive.write_bytes(b"7z")
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="Path = ../../evil.txt\n", stderr="")

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/7z" if name == "7z" else None)
    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(ExtractionError):
        RomExtractor()._extract_7z_cli(archive, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()
    assert [command[1] for command in calls] == ["l"]


def test_file_url_archive_accepted(tmp_path: Path) -> None:
    archive = _make_zip(tmp_path / "rom.zip")
    dest = tmp_path / "out"
    count = RomExtractor().extract(f"file://{archive}", dest)
    assert count == 3
