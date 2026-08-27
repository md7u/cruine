"""DeviceModel: target hardware and source tree repositories."""

from __future__ import annotations

import dataclasses
import re

from cruine.models.base import BaseModel

SUPPORTED_TREE_TYPES = ("device", "kernel", "vendor", "other")


def _field_validator(field_name: str):
    def decorator(fn):
        fn._field_name = field_name
        return staticmethod(fn)
    return decorator


def _model_validator(fn):
    fn._is_model_validator = True
    return fn


@dataclasses.dataclass
class RepositoryModel(BaseModel):
    type: str = "other"
    url: str = ""
    target_path: str = ""
    revision: str | None = None

    def __post_init__(self) -> None:
        missing = [f for f in ("url", "target_path") if not getattr(self, f)]
        if missing:
            raise ValueError(f"required fields missing: {', '.join(missing)}")
        super().__post_init__()

    @_field_validator("type")
    def _validate_type(value: str) -> str:
        value = value.strip().lower()
        if value not in SUPPORTED_TREE_TYPES:
            raise ValueError(
                f"repository type must be one of {SUPPORTED_TREE_TYPES}, got {value!r}"
            )
        return value

    @_field_validator("url")
    def _validate_url(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("repository url must not be empty")
        return value

    @_field_validator("target_path")
    def _validate_target_path(value: str) -> str:
        value = value.strip().strip("/")
        if not value:
            raise ValueError("repository target_path must not be empty")
        if re.search(r"[\s]+", value):
            raise ValueError(f"target_path must not contain whitespace, got {value!r}")
        return value


@dataclasses.dataclass
class LocalFileModel(RepositoryModel):
    @_field_validator("url")
    def _validate_url(value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("file url (local source path) must not be empty")
        return value


@dataclasses.dataclass
class DeviceModel(BaseModel):
    codename: str = ""
    repositories: list[RepositoryModel] = dataclasses.field(default_factory=list)
    files: list[LocalFileModel] = dataclasses.field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.codename:
            raise ValueError("codename is required")
        super().__post_init__()

    @_field_validator("codename")
    def _validate_codename(value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value):
            raise ValueError(f"codename must be a valid device identifier, got {value!r}")
        return value
