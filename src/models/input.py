"""InputModel: an existing ROM archive to extract and repackage."""

from __future__ import annotations

from pydantic import BaseModel, field_validator

SUPPORTED_INPUT_FORMATS: tuple[str, ...] = (
    ".zip",
    ".tar",
    ".tar.gz",
    ".tar.bz2",
    ".tar.xz",
    ".tgz",
    ".7z",
)


class InputModel(BaseModel):
    archive: str | None = None
    format: str | None = None

    @field_validator("archive")
    @classmethod
    def _validate_archive(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("input.archive must not be empty")
        return value

    @field_validator("format")
    @classmethod
    def _validate_format(cls, value: str | None) -> str | None:
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
