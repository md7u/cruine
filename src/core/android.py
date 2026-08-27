"""Native Android format handlers: OTA payload.bin and sparse images.

Implements payload.bin header/metadata parsing and partition extraction
without requiring external tools.  Sparse image (simg) conversion is also
handled natively.  Payload blob decompression uses the stdlib ``gzip`` for
gzip, and the system ``lz4`` / ``zstd`` / ``brotli`` binaries (via
subprocess) for the others — no Python packages are required.
"""

from __future__ import annotations

import gzip
import json
import os
import struct
import subprocess
from pathlib import Path

from cruine.utils.logger import log

# ── payload.bin constants ────────────────────────────────────────────

_PAYLOAD_MAGIC = b"CrAU"
_PAYLOAD_HEADER_FMT = ">4sQQI"  # magic, version, manifest_size, metadata_sig_size
_PAYLOAD_HEADER_SIZE = struct.calcsize(_PAYLOAD_HEADER_FMT)

# ── sparse image constants ──────────────────────────────────────────

_SPARSE_MAGIC = b"\x3aff26cd"
_EROF_MAGIC = b"\x45\x3d\xcd\x28"  # EROFS superblock magic (0x28cd3d45 LE)
_SPARSE_HEADER_FMT = (
    "<IIIIIIII"  # magic, major, minor, hdr_sz, chunk_hdr_sz,
)
_SPARSE_HEADER_SIZE = struct.calcsize(_SPARSE_HEADER_FMT)
_SPARSE_CHUNK_HEADER_FMT = "<IIHh"  # chunk_type, reserved, blocks, total_sz
_SPARSE_CHUNK_HEADER_SIZE = struct.calcsize(_SPARSE_CHUNK_HEADER_FMT)

_CHUNK_TYPE_RAW = 0xCAC1
_CHUNK_TYPE_FILL = 0xCAC2
_CHUNK_TYPE_DONT_CARE = 0xCAC3
_CHUNK_TYPE_CRC32 = 0xCAC4


# ── payload.bin ──────────────────────────────────────────────────────


class PayloadError(RuntimeError):
    """Raised when payload.bin extraction fails."""


def _decompress_blob(
    data: bytes,
    compression: str,
) -> bytes:
    """Decompress a payload data blob.

    Supports ``none``, ``gzip``, ``lz4``, ``zstd``, and ``brotli``.
    gzip is decoded natively (stdlib); lz4/zstd/brotli use the system
    binary via subprocess — no Python package dependencies required.
    """
    if compression == "none":
        return data

    if compression == "gzip":
        return gzip.decompress(data)

    if compression == "lz4":
        proc = subprocess.run(
            ["lz4", "-d", "-f"],
            input=data,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout
        raise PayloadError(f"lz4 decompression failed: {proc.stderr.decode(errors='replace')}")

    if compression == "zstd":
        proc = subprocess.run(
            ["zstd", "-d", "-f", "--stdout"],
            input=data,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout
        raise PayloadError(f"zstd decompression failed: {proc.stderr.decode(errors='replace')}")

    if compression == "brotli":
        proc = subprocess.run(
            ["brotli", "-d", "-c"],
            input=data,
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout
        raise PayloadError(f"brotli decompression failed: {proc.stderr.decode(errors='replace')}")

    raise PayloadError(f"unsupported payload compression: {compression!r}")


def extract_payload(
    payload_bin: Path,
    destination: Path,
    *,
    partition_filter: set[str] | None = None,
) -> int:
    """Parse and extract partition images from an OTA ``payload.bin``.

    Writes each partition image into *destination* as ``<partition>.img``.
    Returns the number of files written.

    If *partition_filter* is given, only listed partition names are
    extracted (useful when only specific partitions are needed).
    """
    with open(payload_bin, "rb") as fh:
        header_raw = fh.read(_PAYLOAD_HEADER_SIZE)
        if len(header_raw) < _PAYLOAD_HEADER_SIZE:
            raise PayloadError(f"{payload_bin.name}: file too small for payload header")
        magic, file_format_version, manifest_size, metadata_sig_size = struct.unpack(
            _PAYLOAD_HEADER_FMT, header_raw,
        )
        if magic != _PAYLOAD_MAGIC:
            raise PayloadError(
                f"{payload_bin.name}: not a valid payload.bin "
                f"(expected magic CrAU, got {magic!r})"
            )
        log.info(
            f"payload.bin v{file_format_version}: "
            f"manifest={manifest_size} bytes, metadata_sig={metadata_sig_size} bytes"
        )
        metadata_bytes = fh.read(manifest_size)
        if len(metadata_bytes) < manifest_size:
            raise PayloadError(f"{payload_bin.name}: truncated metadata")
        fh.seek(metadata_sig_size, os.SEEK_CUR)

        try:
            metadata = json.loads(metadata_bytes)
        except json.JSONDecodeError as exc:
            raise PayloadError(f"{payload_bin.name}: invalid metadata JSON: {exc}") from exc

        partitions = metadata.get("partitions", [])
        blob_pairs = metadata.get("blobs", [])
        log.info(f"payload.bin: {len(partitions)} partition(s), {len(blob_pairs)} blob(s)")

        blob_data = fh.read()

    destination.mkdir(parents=True, exist_ok=True)
    written = 0
    data_offset = 0
    for blob_info in blob_pairs:
        compression = blob_info.get("compression", "none")
        blob_size = blob_info.get("size", 0)
        raw_blob = blob_data[data_offset:data_offset + blob_size]
        data_offset += blob_size
        decompressed = _decompress_blob(raw_blob, compression)
        for partition in partitions:
            name = partition.get("name", "unknown")
            if partition_filter and name not in partition_filter:
                continue
            size = partition.get("size", 0)
            out = destination / f"{name}.img"
            if not out.exists():
                log.info(f"Extracting partition {name!r} ({size} bytes)...")
            with open(out, "ab") as out_fh:
                written += 1
                out_fh.write(decompressed)
    for partition in partitions:
        name = partition.get("name", "unknown")
        if partition_filter and name not in partition_filter:
            continue
        out = destination / f"{name}.img"
        if out.exists():
            log.success(f"Extracted partition {name!r} -> {out}")
    return written


# ── sparse image conversion ──────────────────────────────────────────


def is_sparse_image(path: Path) -> bool:
    """Return ``True`` if *path* has the sparse image magic bytes."""
    try:
        with open(path, "rb") as f:
            return f.read(4) == _SPARSE_MAGIC
    except OSError:
        return False


def is_erofs_image(path: Path) -> bool:
    """Return ``True`` if *path* is an EROFS filesystem image."""
    try:
        with open(path, "rb") as f:
            return f.read(4) == _EROF_MAGIC
    except OSError:
        return False


def convert_sparse_image(src: Path, dst: Path) -> None:
    """Convert a sparse Android image (simg) to a raw image.

    Writes the output to *dst*.  No external tools required.
    """
    with open(src, "rb") as fh:
        hdr_raw = fh.read(_SPARSE_HEADER_SIZE)
        if len(hdr_raw) < _SPARSE_HEADER_SIZE:
            raise PayloadError(f"{src.name}: file too small for sparse header")
        (
            magic, major, minor, hdr_sz,
            chunk_hdr_sz, blk_sz, total_blks,
            total_chunks, _image_checksum,
        ) = struct.unpack(_SPARSE_HEADER_FMT, hdr_raw)
        if magic != int.from_bytes(_SPARSE_MAGIC, "little"):
            raise PayloadError(f"{src.name}: not a sparse image")
        log.info(
            f"sparse image v{major}.{minor}: "
            f"blk_sz={blk_sz}, total_blks={total_blks}, "
            f"chunks={total_chunks}"
        )
        fh.seek(hdr_sz)
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(dst, "wb") as out:
            for _ in range(total_chunks):
                chunk_hdr_raw = fh.read(chunk_hdr_sz)
                if len(chunk_hdr_raw) < chunk_hdr_sz:
                    raise PayloadError(f"{src.name}: truncated chunk header")
                chunk_type, _reserved, blocks, total_sz = struct.unpack(
                    _SPARSE_CHUNK_HEADER_FMT, chunk_hdr_raw,
                )
                data_sz = total_sz - chunk_hdr_sz
                if chunk_type == _CHUNK_TYPE_RAW:
                    remaining = data_sz
                    while remaining > 0:
                        buf = fh.read(min(remaining, 1024 * 1024))
                        if not buf:
                            break
                        out.write(buf)
                        remaining -= len(buf)
                elif chunk_type == _CHUNK_TYPE_FILL:
                    fill_data = fh.read(4)
                    if len(fill_data) < 4:
                        raise PayloadError(f"{src.name}: truncated fill data")
                    out.write(fill_data * (blocks * blk_sz // 4))
                    fh.seek(data_sz - 4, os.SEEK_CUR)
                elif chunk_type == _CHUNK_TYPE_DONT_CARE:
                    out.write(b"\x00" * (blocks * blk_sz))
                    fh.seek(data_sz, os.SEEK_CUR)
                elif chunk_type == _CHUNK_TYPE_CRC32:
                    fh.seek(data_sz, os.SEEK_CUR)
                else:
                    raise PayloadError(
                        f"{src.name}: unknown chunk type 0x{chunk_type:04x}"
                    )
    log.success(f"Converted sparse image {src.name} -> {dst}")
