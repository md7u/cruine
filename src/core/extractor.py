"""ROM archive extraction engine (.zip, .tar, .tar.gz, .tar.xz, .tgz, .7z).

Extraction is path-traversal safe: every member is resolved against the
destination directory and refused if it would land outside of it.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path

from cruine.models.input import SUPPORTED_INPUT_FORMATS
from cruine.utils.logger import log
from cruine.utils.urls import localize_url

__all__ = [
    "SUPPORTED_INPUT_FORMATS",
    "ExtractionError",
    "RomExtractor",
    "detect_format",
]


class ExtractionError(RuntimeError):
    """Raised when archive extraction fails."""


def _safe_member_path(destination: Path, name: str) -> Path:
    """Resolve an archive member name against the destination safely."""
    destination = destination.resolve()
    target = (destination / name).resolve()
    if target != destination and destination not in target.parents:
        raise ExtractionError(f"Archive member escapes the destination directory: {name!r}")
    return target


def detect_format(archive: Path) -> str:
    """Return the normalized archive suffix (e.g. ``.tar.gz``) for a path."""
    lower = str(archive).lower()
    for suffix in (
        ".tar.gz",
        ".tar.bz2",
        ".tar.xz",
        ".tgz",
        ".7z",
        ".zip",
        ".tar",
    ):
        if lower.endswith(suffix):
            return suffix
    raise ExtractionError(
        f"Cannot detect archive format for {archive.name}; "
        f"supported: {', '.join(SUPPORTED_INPUT_FORMATS)}"
    )


class RomExtractor:
    """Extracts a ROM archive into a directory, ready for editing or repack."""

    def __init__(self, workspace: Path | None = None) -> None:
        self.workspace = Path(workspace) if workspace is not None else None

    def product_dir(self, codename: str) -> Path:
        assert self.workspace is not None
        return self.workspace / "out" / "target" / "product" / codename

    def extract(self, archive: str, destination: Path) -> int:
        """Extract ``archive`` into ``destination``.

        Returns the number of regular files extracted. ``destination`` is
        created if missing.
        """
        archive = Path(localize_url(archive))
        if not archive.is_file():
            raise ExtractionError(f"ROM archive does not exist: {archive}")
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        fmt = detect_format(archive)
        log.info(f"Extracting {archive.name} ({fmt}) -> {destination}")
        if fmt in (".zip",):
            count = self._extract_zip(archive, destination)
        elif fmt == ".7z":
            count = self._extract_7z(archive, destination)
        else:
            count = self._extract_tar(archive, destination)
        log.success(f"Extracted {count} file(s) from {archive.name} into {destination}")
        return count

    def _extract_zip(self, archive: Path, destination: Path) -> int:
        count = 0
        try:
            with zipfile.ZipFile(archive) as zf:
                for member in zf.infolist():
                    name = member.filename
                    target = _safe_member_path(destination, name)
                    mode = member.external_attr >> 16
                    if name.endswith("/"):
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if stat.S_ISLNK(mode):
                        link = zf.read(member).decode("utf-8", errors="replace")
                        _write_symlink(target, link)
                        count += 1
                    else:
                        with zf.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        count += 1
        except zipfile.BadZipFile as exc:
            raise ExtractionError(f"Not a valid zip archive: {archive.name}: {exc}") from exc
        return count

    def _extract_tar(self, archive: Path, destination: Path) -> int:
        count = 0
        try:
            with tarfile.open(archive, mode="r:*") as tf:
                for member in tf.getmembers():
                    target = _safe_member_path(destination, member.name)
                    mode = member.mode & 0o7777
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                        if mode & 0o111:
                            target.chmod(mode)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if member.issym():
                        _write_symlink(target, member.linkname)
                        count += 1
                    elif member.islnk():
                        link_target = _safe_member_path(destination, member.linkname)
                        _write_symlink(target, str(link_target))
                        count += 1
                    elif member.isreg():
                        src = tf.extractfile(member)
                        if src is None:
                            continue
                        with src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                        if mode:
                            target.chmod(mode)
                        count += 1
        except tarfile.TarError as exc:
            raise ExtractionError(f"Not a valid tar archive: {archive.name}: {exc}") from exc
        return count

    def _extract_7z(self, archive: Path, destination: Path) -> int:
        try:
            import py7zr
        except ImportError:
            return self._extract_7z_cli(archive, destination)
        try:
            with py7zr.SevenZipFile(archive) as zf:
                for info in zf.list():
                    name = info.filename if hasattr(info, "filename") else info.name
                    _safe_member_path(destination, name)
                zf.extractall(path=str(destination))
        except Exception as exc:
            raise ExtractionError(f"7z extraction failed: {exc}") from exc
        return sum(1 for _ in destination.rglob("*") if _.is_file())

    def _extract_7z_cli(self, archive: Path, destination: Path) -> int:
        sevenz = shutil.which("7z")
        if not sevenz:
            raise ExtractionError(
                "7z extraction requested but neither py7zr nor the '7z' binary is available"
            )
        listed = subprocess.run(
            [sevenz, "l", "-slt", str(archive)],
            capture_output=True,
            text=True,
            check=False,
        )
        if listed.returncode != 0:
            raise ExtractionError(
                "7z listing failed: "
                + ((listed.stderr or "").strip() or (listed.stdout or "")[-500:])
            )
        for line in listed.stdout.splitlines():
            if line.startswith("Path = "):
                _safe_member_path(destination, line[len("Path = ") :].strip())
        proc = subprocess.run(
            [sevenz, "x", "-y", f"-o{destination}", str(archive)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise ExtractionError(
                f"7z extraction failed: {(proc.stderr or '').strip() or (proc.stdout or '')[-500:]}"
            )
        return sum(1 for _ in destination.rglob("*") if _.is_file())


def _write_symlink(target: Path, link: str) -> None:
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(link)
