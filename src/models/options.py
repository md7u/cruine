"""OptionsModel: build options and behaviour flags."""

from __future__ import annotations

import dataclasses
import re

from cruine.models.base import BaseModel

_CCACHE_SIZE_RE = re.compile(r"^\d+(\.\d+)?[KMG]?$", re.IGNORECASE)
_BUILD_VARIANTS = ("eng", "user", "userdebug")


def _field_validator(field_name: str):
    def decorator(fn):
        fn._field_name = field_name
        return staticmethod(fn)
    return decorator


@dataclasses.dataclass
class OptionsModel(BaseModel):
    use_ccache: bool = True
    ccache_size: str = "50G"
    clean_build: bool = False
    build_variant: str = "userdebug"
    parallel_jobs: int | None = None
    extra_make_args: list[str] = dataclasses.field(default_factory=list)
    build_container: str | None = None

    @_field_validator("ccache_size")
    def _validate_ccache_size(value: str) -> str:
        value = value.strip().upper()
        if not _CCACHE_SIZE_RE.match(value):
            raise ValueError(f"ccache_size must look like '50G', '4G' or '800M', got {value!r}")
        return value

    @_field_validator("build_variant")
    def _validate_build_variant(value: str) -> str:
        value = value.strip().lower()
        if value not in _BUILD_VARIANTS:
            raise ValueError(f"build_variant must be one of {_BUILD_VARIANTS}, got {value!r}")
        return value

    @_field_validator("parallel_jobs")
    def _validate_parallel_jobs(value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("parallel_jobs must be a positive integer")
        return value
