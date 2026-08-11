"""OutputModel: archive format and output options."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class OutputFormat(str, Enum):
    ZIP = ".zip"
    TAR_GZ = ".tar.gz"
    TAR_BZ2 = ".tar.bz2"
    TAR_XZ = ".tar.xz"
    TGZ = ".tgz"
    SEVENZ = ".7z"
    IMG = ".img"
    ISO = ".iso"
    TAR = ".tar"


class OutputModel(BaseModel):
    format: OutputFormat = OutputFormat.ZIP
    custom_name: str | None = None
    compression_level: int = Field(default=6, ge=0, le=9)
    exclude_dirs: list[str] = Field(default_factory=lambda: ["obj", "symbols"])

    @field_validator("format", mode="before")
    @classmethod
    def _normalize_format(cls, value: object) -> object:
        if isinstance(value, OutputFormat):
            return value
        if isinstance(value, str):
            fmt = value.strip().lower()
            if not fmt.startswith("."):
                fmt = f".{fmt}"
            return OutputFormat(fmt)
        return value

    @field_validator("custom_name")
    @classmethod
    def _sanitize_custom_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        return value

    @property
    def extension(self) -> str:
        return self.format.value
