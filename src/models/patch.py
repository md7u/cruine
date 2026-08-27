"""PatchModel and HookModel: tree patching and lifecycle hooks."""

from __future__ import annotations

import dataclasses
from typing import Literal

from cruine.models.base import BaseModel

HookPhase = Literal["pre_fetch", "post_fetch", "pre_build", "post_build"]


def _field_validator(field_name: str):
    def decorator(fn):
        fn._field_name = field_name
        return staticmethod(fn)
    return decorator


@dataclasses.dataclass
class PatchModel(BaseModel):
    file: str = ""
    directory: str = "."
    strip: int = 1

    def __post_init__(self) -> None:
        if not (0 <= self.strip <= 2):
            raise ValueError("strip must be between 0 and 2")
        super().__post_init__()

    @_field_validator("file")
    def _validate_file(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("patch file must not be empty")
        return value


@dataclasses.dataclass
class HookModel(BaseModel):
    name: str = ""
    command: str = ""
    phase: HookPhase = "pre_build"
    workdir: str = "."

    @_field_validator("name")
    def _validate_name(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("hook name must not be empty")
        return value

    @_field_validator("command")
    def _validate_command(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("hook command must not be empty")
        return value
