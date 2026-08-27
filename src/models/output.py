"""OutputModel: archive format and output options."""

from __future__ import annotations

import dataclasses
from enum import Enum

from cruine.models.base import BaseModel, ValidationError


def _field_validator(field_name: str):
    def decorator(fn):
        fn._field_name = field_name
        return staticmethod(fn)
    return decorator


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


@dataclasses.dataclass
class OutputModel(BaseModel):
    format: OutputFormat = OutputFormat.ZIP
    custom_name: str | None = None
    compression_level: int = 6
    exclude_dirs: list[str] = dataclasses.field(default_factory=lambda: ["obj", "symbols"])

    def __post_init__(self) -> None:
        if isinstance(self.format, str):
            fmt = self.format.strip().lower()
            if not fmt.startswith("."):
                fmt = f".{fmt}"
            try:
                self.format = OutputFormat(fmt)
            except ValueError as exc:
                raise ValidationError(
                    [{"loc": "format", "msg": str(exc), "type": "value_error"}]
                ) from exc
        if not (0 <= self.compression_level <= 9):
            raise ValidationError(
                [
                    {
                        "loc": "compression_level",
                        "msg": "must be between 0 and 9",
                        "type": "value_error",
                    }
                ]
            )
        super().__post_init__()

    @_field_validator("custom_name")
    def _sanitize_custom_name(value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        return value

    @property
    def extension(self) -> str:
        return self.format.value
