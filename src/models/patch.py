"""PatchModel and HookModel: tree patching and lifecycle hooks."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

HookPhase = Literal["pre_fetch", "post_fetch", "pre_build", "post_build"]


class PatchModel(BaseModel):
    file: str
    directory: str = "."
    strip: int = Field(default=1, ge=0, le=2)

    @field_validator("file")
    @classmethod
    def _validate_file(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("patch file must not be empty")
        return value


class HookModel(BaseModel):
    name: str
    command: str
    phase: HookPhase = "pre_build"
    workdir: str = "."

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("hook name must not be empty")
        return value

    @field_validator("command")
    @classmethod
    def _validate_command(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("hook command must not be empty")
        return value
