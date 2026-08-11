"""ROMModel: upstream manifest and build configuration."""

from __future__ import annotations

import re

from pydantic import BaseModel, field_validator


class ROMModel(BaseModel):
    source: str
    branch: str
    lunch_prefix: str
    build_target: str
    manifest: str | None = None
    groups: str | None = None
    depth: int | None = None

    @field_validator("source")
    @classmethod
    def _validate_source(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("source must not be empty")
        return value

    @field_validator("branch")
    @classmethod
    def _validate_branch(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("branch must not be empty")
        if re.search(r"[\s]+", value):
            raise ValueError(f"branch must not contain whitespace, got {value!r}")
        return value

    @field_validator("lunch_prefix")
    @classmethod
    def _validate_lunch_prefix(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
            raise ValueError(f"lunch_prefix must be a valid identifier, got {value!r}")
        return value

    @field_validator("build_target")
    @classmethod
    def _validate_build_target(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("build_target must not be empty")
        return value

    @field_validator("depth")
    @classmethod
    def _validate_depth(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("depth must be a positive integer")
        return value
