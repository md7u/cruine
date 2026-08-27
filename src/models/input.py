"""InputModel: an existing ROM archive to extract and repackage."""

from __future__ import annotations

import dataclasses

from cruine.models.base import BaseModel

SUPPORTED_INPUT_FORMATS: tuple[str, ...] = (
    ".zip",
    ".tar",
    ".tar.gz",
    ".tar.bz2",
    ".tar.xz",
    ".tgz",
    ".7z",
)


def _field_validator(field_name: str):
    def decorator(fn):
        fn._field_name = field_name
        return staticmethod(fn)
    return decorator


@dataclasses.dataclass
class InputModel(BaseModel):
    archive: str | None = None
    format: str | None = None

    @_field_validator("archive")
    def _validate_archive(value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("input.archive must not be empty")
        return value

    @_field_validator("format")
    def _validate_format(value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().lower()
        if not value.startswith("."):
            value = f".{value}"
        if value not in SUPPORTED_INPUT_FORMATS:
            raise ValueError(
                f"input.format must be one of {', '.join(SUPPORTED_INPUT_FORMATS)}, got {value!r}"
            )
        return value
