"""ROMModel: upstream manifest and build configuration."""

from __future__ import annotations

import dataclasses
import re

from cruine.models.base import BaseModel


def _field_validator(field_name: str):
    def decorator(fn):
        fn._field_name = field_name
        return staticmethod(fn)
    return decorator


@dataclasses.dataclass
class ROMModel(BaseModel):
    source: str = ""
    branch: str = ""
    lunch_prefix: str = ""
    build_target: str = ""
    manifest: str | None = None
    groups: str | None = None
    depth: int | None = None

    def __post_init__(self) -> None:
        missing = [
            f
            for f in ("source", "branch", "lunch_prefix", "build_target")
            if not getattr(self, f)
        ]
        if missing:
            raise ValueError(f"required fields missing: {', '.join(missing)}")
        super().__post_init__()

    @_field_validator("source")
    def _validate_source(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("source must not be empty")
        return value

    @_field_validator("branch")
    def _validate_branch(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("branch must not be empty")
        if re.search(r"[\s]+", value):
            raise ValueError(f"branch must not contain whitespace, got {value!r}")
        return value

    @_field_validator("lunch_prefix")
    def _validate_lunch_prefix(value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
            raise ValueError(f"lunch_prefix must be a valid identifier, got {value!r}")
        return value

    @_field_validator("build_target")
    def _validate_build_target(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("build_target must not be empty")
        return value

    @_field_validator("depth")
    def _validate_depth(value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("depth must be a positive integer")
        return value
