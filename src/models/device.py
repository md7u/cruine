"""DeviceModel: target hardware and source tree repositories."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

SUPPORTED_TREE_TYPES = ("device", "kernel", "vendor", "other")


class RepositoryModel(BaseModel):
    type: str = "other"
    url: str
    target_path: str

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in SUPPORTED_TREE_TYPES:
            raise ValueError(
                f"repository type must be one of {SUPPORTED_TREE_TYPES}, got {value!r}"
            )
        return value

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("repository url must not be empty")
        return value

    @field_validator("target_path")
    @classmethod
    def _validate_target_path(cls, value: str) -> str:
        value = value.strip().strip("/")
        if not value:
            raise ValueError("repository target_path must not be empty")
        if re.search(r"[\s]+", value):
            raise ValueError(f"target_path must not contain whitespace, got {value!r}")
        return value


class LocalFileModel(RepositoryModel):
    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("file url (local source path) must not be empty")
        return value


class DeviceModel(BaseModel):
    codename: str
    repositories: list[RepositoryModel] = Field(default_factory=list)
    files: list[LocalFileModel] = Field(default_factory=list)

    @field_validator("codename")
    @classmethod
    def _validate_codename(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value):
            raise ValueError(f"codename must be a valid device identifier, got {value!r}")
        return value
