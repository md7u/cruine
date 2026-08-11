"""OptionsModel: build options and behaviour flags."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_CCACHE_SIZE_RE = re.compile(r"^\d+(\.\d+)?[KMG]?$", re.IGNORECASE)
_BUILD_VARIANTS = ("eng", "user", "userdebug")


class OptionsModel(BaseModel):
    use_ccache: bool = True
    ccache_size: str = "50G"
    clean_build: bool = False
    build_variant: str = "userdebug"
    parallel_jobs: int | None = None
    extra_make_args: list[str] = Field(default_factory=list)

    @field_validator("ccache_size")
    @classmethod
    def _validate_ccache_size(cls, value: str) -> str:
        value = value.strip().upper()
        if not _CCACHE_SIZE_RE.match(value):
            raise ValueError(f"ccache_size must look like '50G', '4G' or '800M', got {value!r}")
        return value

    @field_validator("build_variant")
    @classmethod
    def _validate_build_variant(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in _BUILD_VARIANTS:
            raise ValueError(f"build_variant must be one of {_BUILD_VARIANTS}, got {value!r}")
        return value

    @field_validator("parallel_jobs")
    @classmethod
    def _validate_parallel_jobs(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("parallel_jobs must be a positive integer")
        return value
