"""Archive packaging module (.zip, .tar.gz, .tar.bz2, .tar.xz, .tgz, .7z, .img, .iso, .tar)."""

from __future__ import annotations

import bz2
import gzip
import lzma
import os
import shutil
import subprocess
import tarfile
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path

from cruine.models.output import OutputFormat
from cruine.models.recipe import RecipeSchema
from cruine.utils.logger import log


class PackagingError(RuntimeError):
    """Raised when output packaging fails."""


def _tar_member_filter(member: tarfile.TarInfo) -> tarfile.TarInfo | None:
    if member.isfile() or member.isdir() or member.issym() or member.islnk():
        member.uid = 0
        member.gid = 0
        member.uname = ""
        member.gname = ""
        return member
    return None


class OutputPackager:
    """Locates raw build outputs and packages them into the requested format."""

    PRIMARY_IMG_CANDIDATES = ("system.img", "vendor.img", "boot.img", "recovery.img", "dtbo.img")

    def __init__(
        self,
        recipe: RecipeSchema,
        workspace: Path,
        destination: Path,
        source_dir: Path | None = None,
    ) -> None:
        self.recipe = recipe
        self.workspace = Path(workspace)
        self.destination = Path(destination)
        self._source_dir = Path(source_dir) if source_dir is not None else None
        self._exclude_dirs = set(self.recipe.output.exclude_dirs)

    def output_dir(self) -> Path:
        if self._source_dir is not None:
            return self._source_dir
        return self.workspace / "out" / "target" / "product" / self.recipe.device.codename

    def package(self) -> Path:
        output_model = self.recipe.output
        out_dir = self.output_dir()
        if not out_dir.is_dir():
            raise PackagingError(
                f"Build output directory not found: {out_dir}\n"
                "Run the build first, or check device.codename in rc.json."
            )
        if self.destination.exists() and not self.destination.is_dir():
            raise PackagingError(f"Destination exists and is not a directory: {self.destination}")
        self.destination.mkdir(parents=True, exist_ok=True)

        base = output_model.custom_name or (
            f"{self.recipe.project_name}-{self.recipe.device.codename}"
        )
        fmt = output_model.format
        log.info(f"Packaging {fmt.value} from {out_dir}")
        if fmt == OutputFormat.IMG:
            target = self.destination / f"{base}.img"
            self._package_img(out_dir, target)
        elif fmt == OutputFormat.ISO:
            target = self.destination / f"{base}.iso"
            self._package_iso(out_dir, target)
        else:
            target = self.destination / f"{base}{fmt.value}"
            self._make_archive(fmt, out_dir, target, output_model.compression_level)
        log.success(f"Packaged -> {target} ({self._human_size(target.stat().st_size)})")
        return target

    @staticmethod
    def _human_size(num_bytes: int) -> str:
        value = float(num_bytes)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.1f} {unit}"
            value /= 1024
        return f"{num_bytes} B"

    def _walk(self, root: Path) -> Iterator[tuple[Path, list[str], list[str]]]:
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = [d for d in sorted(dirnames) if d not in self._exclude_dirs]
            yield Path(dirpath), dirnames, sorted(filenames)

    def _make_archive(self, fmt: OutputFormat, out_dir: Path, target: Path, level: int) -> None:
        log.info(f"Creating {fmt.value} archive (compression level {level})...")
        if fmt == OutputFormat.ZIP:
            self._make_zip(out_dir, target, level)
        elif fmt in (
            OutputFormat.TAR,
            OutputFormat.TAR_GZ,
            OutputFormat.TAR_BZ2,
            OutputFormat.TAR_XZ,
            OutputFormat.TGZ,
        ):
            self._make_tar(fmt, out_dir, target, level)
        elif fmt == OutputFormat.SEVENZ:
            self._make_7z(out_dir, target, level)
        else:
            raise PackagingError(f"Unsupported format: {fmt}")

    def _make_zip(self, out_dir: Path, target: Path, level: int) -> None:
        with zipfile.ZipFile(
            target,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=level,
        ) as zf:
            for dirpath, dirnames, filenames in self._walk(out_dir):
                rel_dir = dirpath.relative_to(out_dir).as_posix()
                for name in dirnames:
                    entry = dirpath / name
                    arc = f"{rel_dir}/{name}/" if rel_dir != "." else f"{name}/"
                    self._zip_add_entry(zf, entry, arc)
                for name in filenames:
                    entry = dirpath / name
                    arc = f"{rel_dir}/{name}" if rel_dir != "." else name
                    if entry.is_symlink():
                        self._zip_add_entry(zf, entry, arc)
                    else:
                        zf.write(entry, arc)

    @staticmethod
    def _zip_add_entry(zf: zipfile.ZipFile, entry: Path, arc: str) -> None:
        stat = entry.stat(follow_symlinks=False)
        info = zipfile.ZipInfo(arc, date_time=time.localtime(stat.st_mtime))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = (stat.st_mode & 0xFFFF) << 16
        if entry.is_symlink():
            zf.writestr(info, os.readlink(entry))
        else:
            zf.writestr(info, b"")

    def _make_tar(self, fmt: OutputFormat, out_dir: Path, target: Path, level: int) -> None:
        if fmt == OutputFormat.TAR:
            with tarfile.open(target, "w") as tf:
                self._tar_add_tree(tf, out_dir)
        elif fmt in (OutputFormat.TAR_GZ, OutputFormat.TGZ):
            with (
                gzip.GzipFile(filename=str(target), mode="wb", compresslevel=level) as gz,
                tarfile.open(fileobj=gz, mode="w") as tf,
            ):
                self._tar_add_tree(tf, out_dir)
        elif fmt == OutputFormat.TAR_BZ2:
            with (
                bz2.open(target, "wb", compresslevel=level) as bz,
                tarfile.open(fileobj=bz, mode="w") as tf,
            ):
                self._tar_add_tree(tf, out_dir)
        else:
            with (
                lzma.open(target, "wb", preset=level) as lz,
                tarfile.open(fileobj=lz, mode="w") as tf,
            ):
                self._tar_add_tree(tf, out_dir)

    def _tar_add_tree(self, tf: tarfile.TarFile, out_dir: Path) -> None:
        try:
            filter_kwargs = {"filter": _tar_member_filter}
        except TypeError:  # pragma: no cover - older Python
            filter_kwargs = {}
        for dirpath, _, filenames in self._walk(out_dir):
            rel = dirpath.relative_to(out_dir).as_posix()
            if rel != ".":
                tf.add(dirpath, arcname=rel, recursive=False, **filter_kwargs)
            for name in filenames:
                entry = dirpath / name
                arc = f"{rel}/{name}" if rel != "." else name
                tf.add(entry, arcname=arc, recursive=False, **filter_kwargs)

    def _make_7z(self, out_dir: Path, target: Path, level: int) -> None:
        try:
            import py7zr
        except ImportError:
            self._make_7z_cli(out_dir, target, level)
            return
        try:
            with py7zr.SevenZipFile(
                target, "w", filters=[{"id": py7zr.FILTER_LZMA2, "preset": level}]
            ) as archive:
                for dirpath, _, filenames in self._walk(out_dir):
                    rel = dirpath.relative_to(out_dir).as_posix()
                    for name in filenames:
                        entry = dirpath / name
                        arc = f"{rel}/{name}" if rel != "." else name
                        archive.write(entry, arcname=arc)
        except Exception as exc:
            raise PackagingError(f"7z packaging failed: {exc}") from exc

    def _make_7z_cli(self, out_dir: Path, target: Path, level: int) -> None:
        sevenz = shutil.which("7z")
        if not sevenz:
            raise PackagingError(
                "7z packaging requested but neither py7zr nor the '7z' binary is available"
            )
        command = [
            sevenz,
            "a",
            "-t7z",
            f"-mx={level}",
            str(target),
            "*",
        ]
        for excluded in sorted(self._exclude_dirs):
            command.append(f"-xr!{excluded}")
        proc = subprocess.run(
            command, cwd=str(out_dir), capture_output=True, text=True, check=False
        )
        if proc.returncode != 0:
            raise PackagingError(
                f"7z failed: {(proc.stderr or '').strip() or (proc.stdout or '')[-500:]}"
            )

    def _package_img(self, out_dir: Path, target: Path) -> None:
        chosen: Path | None = None
        for name in self.PRIMARY_IMG_CANDIDATES:
            candidate = out_dir / name
            if candidate.is_file():
                chosen = candidate
                break
        if chosen is None:
            images = sorted(
                (p for p in out_dir.glob("*.img") if p.is_file()),
                key=lambda p: p.stat().st_size,
            )
            if not images:
                raise PackagingError(f"No .img files found in {out_dir}")
            chosen = images[-1]
        log.info(f"Packaging raw image: {chosen.name}")
        shutil.copy2(chosen, target)

    def _package_iso(self, out_dir: Path, target: Path) -> None:
        tool = shutil.which("mkisofs") or shutil.which("genisoimage") or shutil.which("xorriso")
        if tool:
            self._iso_cli(tool, out_dir, target)
            return
        try:
            import pycdlib
        except ImportError:
            raise PackagingError(
                "ISO packaging requested but neither pycdlib nor "
                "mkisofs/genisoimage/xorriso is available"
            ) from None
        iso = pycdlib.PyCdlib()
        iso.new(interchange_level=4, joliet=3, rock_ridge="1.09")
        try:
            self._iso_add_tree(iso, out_dir, out_dir)
            iso.write(str(target))
        except Exception as exc:
            raise PackagingError(f"ISO packaging failed: {exc}") from exc
        finally:
            iso.close()

    def _iso_cli(self, tool: str, out_dir: Path, target: Path) -> None:
        if Path(tool).name == "xorriso":
            command = [
                tool,
                "-as",
                "mkisofs",
                "-quiet",
                "-R",
                "-J",
                "-o",
                str(target),
                str(out_dir),
            ]
        else:
            command = [tool, "-quiet", "-R", "-J", "-o", str(target), str(out_dir)]
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise PackagingError(
                f"ISO creation failed: {(proc.stderr or '').strip() or (proc.stdout or '')[-500:]}"
            )

    def _iso_add_tree(self, iso, base: Path, current: Path) -> None:
        for entry in sorted(current.iterdir()):
            if entry.name in self._exclude_dirs and entry.is_dir():
                continue
            if entry.is_dir() and not entry.is_symlink():
                rel = entry.relative_to(base).as_posix()
                iso.add_directory(f"/{rel.upper()}", rr_name=rel, joliet_path=f"/{rel}")
                self._iso_add_tree(iso, base, entry)
            elif entry.is_file():
                rel = entry.relative_to(base).as_posix()
                try:
                    with open(entry, "rb") as handle:
                        iso.add_fp(handle, f"/{rel.upper()}", rr_name=rel, joliet_path=f"/{rel}")
                except OSError:
                    log.warning(f"Skipping unreadable file in ISO: {rel}")
