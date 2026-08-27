"""ROM archive extraction engine (.zip, .tar, .tar.gz, .tar.xz, .tgz, .7z).

Extraction is path-traversal safe: every member is resolved against the
destination directory and refused if it would land outside of it.

**Modern Android support:** Archives containing ``payload.bin`` (OTA
images) are parsed natively — partition images are extracted and
decompressed inline.  Sparse images (``simg``) are converted to raw
images natively.  ``super.img`` (dynamic partitions) is handled via
``lpunpack`` when available.
"""

from __future__ import annotations

import shutil
import stat
import subprocess
import tarfile
import zipfile
from pathlib import Path

from cruine.core.android import (
    PayloadError,
    convert_sparse_image,
    extract_payload,
    is_erofs_image,
    is_sparse_image,
)
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


def _unpack_super_img(super_img: Path, destination: Path) -> int:
    """Unpack a super.img (dynamic partitions) into individual images.

    Uses ``lpunpack`` if available.
    """
    tool = shutil.which("lpunpack")
    if not tool:
        raise ExtractionError(
            f"{super_img.name}: super.img detected (dynamic partitions) but "
            "'lpunpack' is not installed.  Install it to unpack:\n"
            "  Arch:   yay -S lpunpack\n"
            "  Debian: apt install lpunpack\n"
            "  Manual: https://github.com/nicknumb/buildroot_vendor_amlogic_common/"
            "tree/master/tools/lpunpack"
        )
    log.info("Unpacking super.img via lpunpack...")
    proc = subprocess.run(
        [tool, str(super_img), str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise ExtractionError(
            "lpunpack failed:\n"
            + ((proc.stderr or "").strip() or (proc.stdout or "")[-500:])
        )
    count = sum(1 for f in destination.iterdir() if f.is_file())
    log.success(f"Unpacked {count} partition image(s) from super.img")
    return count


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


def _normalize_format_hint(hint: str) -> str:
    """Normalize a configured format hint to a supported archive suffix."""
    fmt = hint.strip().lower()
    if not fmt.startswith("."):
        fmt = f".{fmt}"
    if fmt not in SUPPORTED_INPUT_FORMATS:
        raise ExtractionError(
            f"Unsupported input format {fmt!r}; supported: {', '.join(SUPPORTED_INPUT_FORMATS)}"
        )
    return fmt


class RomExtractor:
    """Extracts a ROM archive into a directory, ready for editing or repack."""

    def __init__(self, workspace: Path | None = None) -> None:
        self.workspace = Path(workspace) if workspace is not None else None

    def product_dir(self, codename: str) -> Path:
        assert self.workspace is not None
        return self.workspace / "out" / "target" / "product" / codename

    def extract(self, archive: str, destination: Path, format_hint: str | None = None) -> int:
        """Extract ``archive`` into ``destination``.

        Returns the number of regular files extracted. ``destination`` is
        created if missing. When ``format_hint`` is provided (a suffix like
        ``.zip``, e.g. from a recipe's ``input.format``) it takes precedence
        over suffix-based detection.

        Archives containing ``payload.bin`` are handled by parsing the OTA
        payload natively and extracting individual partition images before
        continuing with the remaining archive contents.
        """
        archive = Path(localize_url(archive))
        if not archive.is_file():
            raise ExtractionError(f"ROM archive does not exist: {archive}")
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)

        if archive.suffix.lower() == ".img":
            self._handle_standalone_img(archive, destination)
            return sum(1 for _ in destination.rglob("*") if _.is_file())

        fmt = _normalize_format_hint(format_hint) if format_hint else detect_format(archive)
        log.info(f"Extracting {archive.name} ({fmt}) -> {destination}")
        if fmt in (".zip",):
            count = self._extract_zip(archive, destination)
        elif fmt == ".7z":
            count = self._extract_7z(archive, destination)
        else:
            count = self._extract_tar(archive, destination)
        log.success(f"Extracted {count} file(s) from {archive.name} into {destination}")
        return count

    def _handle_standalone_img(self, img: Path, destination: Path) -> None:
        """Handle a standalone .img file passed as input.archive."""
        name = img.name
        if name == "super.img":
            _unpack_super_img(img, destination)
        elif is_sparse_image(img):
            raw = destination / f"{name}.raw"
            convert_sparse_image(img, raw)
        elif is_erofs_image(img):
            dest = destination / name
            shutil.copy2(img, dest)
            log.info(f"Copied EROFS image {name} -> {dest} (read-only, unmodifiable)")
        else:
            dest = destination / name
            shutil.copy2(img, dest)
            log.info(f"Copied {name} -> {dest}")

    def _extract_zip(self, archive: Path, destination: Path) -> int:
        count = 0
        try:
            with zipfile.ZipFile(archive) as zf:
                names = zf.namelist()
                has_payload = any(Path(n).name == "payload.bin" for n in names)
                has_super = any(Path(n).name == "super.img" for n in names)
                if has_payload:
                    count += self._extract_zip_payload(zf, destination)
                elif has_super:
                    count += self._extract_zip_super(zf, destination)
                for member in zf.infolist():
                    name = member.filename
                    basename = Path(name).name
                    if has_payload and basename in ("payload.bin", "payload_properties.txt"):
                        continue
                    if has_super and basename == "super.img":
                        continue
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

    def _extract_zip_payload(self, zf: zipfile.ZipFile, destination: Path) -> int:
        """Extract payload.bin from a zip, then unpack natively."""
        payload_entry = next(
            (n for n in zf.namelist() if Path(n).name == "payload.bin"), None,
        )
        if payload_entry is None:
            return 0
        payload_bin = destination / "payload.bin"
        log.info("Extracting payload.bin from archive...")
        with zf.open(payload_entry) as src, open(payload_bin, "wb") as dst:
            shutil.copyfileobj(src, dst)
        try:
            return extract_payload(payload_bin, destination)
        except PayloadError as exc:
            raise ExtractionError(str(exc)) from exc
        finally:
            if payload_bin.exists():
                payload_bin.unlink()

    def _extract_zip_super(self, zf: zipfile.ZipFile, destination: Path) -> int:
        """Extract super.img from a zip, then unpack with lpunpack."""
        super_entry = next(
            (n for n in zf.namelist() if Path(n).name == "super.img"), None,
        )
        if super_entry is None:
            return 0
        super_img = destination / "super.img"
        log.info("Extracting super.img from archive...")
        with zf.open(super_entry) as src, open(super_img, "wb") as dst:
            shutil.copyfileobj(src, dst)
        try:
            return _unpack_super_img(super_img, destination)
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError(f"super.img extraction failed: {exc}") from exc
        finally:
            if super_img.exists():
                super_img.unlink()

    def _extract_tar(self, archive: Path, destination: Path) -> int:
        count = 0
        try:
            with tarfile.open(archive, mode="r:*") as tf:
                names = tf.getnames()
                has_payload = any(Path(n).name == "payload.bin" for n in names)
                has_super = any(Path(n).name == "super.img" for n in names)
                if has_payload:
                    count += self._extract_tar_payload(tf, destination)
                elif has_super:
                    count += self._extract_tar_super(tf, destination)
                for member in tf.getmembers():
                    basename = Path(member.name).name
                    if has_payload and basename in ("payload.bin", "payload_properties.txt"):
                        continue
                    if has_super and basename == "super.img":
                        continue
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

    def _extract_tar_payload(self, tf: tarfile.TarFile, destination: Path) -> int:
        """Extract payload.bin from a tar, then unpack natively."""
        payload_member = next(
            (tf.getmember(n) for n in tf.getnames() if Path(n).name == "payload.bin"),
            None,
        )
        if payload_member is None:
            return 0
        payload_bin = destination / "payload.bin"
        log.info("Extracting payload.bin from archive...")
        src = tf.extractfile(payload_member)
        if src is None:
            return 0
        with src, open(payload_bin, "wb") as dst:
            shutil.copyfileobj(src, dst)
        try:
            return extract_payload(payload_bin, destination)
        except PayloadError as exc:
            raise ExtractionError(str(exc)) from exc
        finally:
            if payload_bin.exists():
                payload_bin.unlink()

    def _extract_tar_super(self, tf: tarfile.TarFile, destination: Path) -> int:
        """Extract super.img from a tar, then unpack with lpunpack."""
        super_member = next(
            (tf.getmember(n) for n in tf.getnames() if Path(n).name == "super.img"),
            None,
        )
        if super_member is None:
            return 0
        super_img = destination / "super.img"
        log.info("Extracting super.img from archive...")
        src = tf.extractfile(super_member)
        if src is None:
            return 0
        with src, open(super_img, "wb") as dst:
            shutil.copyfileobj(src, dst)
        try:
            return _unpack_super_img(super_img, destination)
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError(f"super.img extraction failed: {exc}") from exc
        finally:
            if super_img.exists():
                super_img.unlink()

    def _extract_7z(self, archive: Path, destination: Path) -> int:
        return self._extract_7z_cli(archive, destination)

    def _extract_7z_cli(self, archive: Path, destination: Path) -> int:
        sevenz = shutil.which("7z")
        if not sevenz:
            raise ExtractionError(
                "7z extraction requires the '7z' binary (p7zip) to be installed"
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
        count = sum(1 for _ in destination.rglob("*") if _.is_file())
        for p in destination.rglob("payload.bin"):
            count += extract_payload(p, destination)
            p.unlink()
        for p in destination.rglob("super.img"):
            count += _unpack_super_img(p, destination)
            p.unlink()
        for p in destination.rglob("*.img"):
            if is_sparse_image(p):
                raw = p.with_suffix(p.suffix + ".raw")
                convert_sparse_image(p, raw)
                count += 1
        return count


def _write_symlink(target: Path, link: str) -> None:
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(link)
