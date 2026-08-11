"""Pydantic schema validation models."""

from __future__ import annotations

from typing import Any

from cruine.models.output import OutputFormat
from cruine.models.recipe import RecipeSchema
from pydantic import ValidationError


class RecipeValidator:
    """Validates raw recipe dictionaries against the pydantic schema."""

    @classmethod
    def validate_dict(cls, data: dict[str, Any]) -> RecipeSchema:
        if not isinstance(data, dict):
            raise TypeError("Recipe root must be a JSON object")
        try:
            return RecipeSchema.model_validate(data)
        except ValidationError as exc:
            details = []
            for error in exc.errors():
                location = ".".join(str(part) for part in error["loc"]) or "<root>"
                details.append(f"  - {location}: {error['msg']} (type={error['type']})")
            raise ValueError("rc.json failed schema validation:\n" + "\n".join(details)) from exc

    @staticmethod
    def normalize_format(value: str) -> OutputFormat:
        fmt = value.strip().lower()
        if not fmt.startswith("."):
            fmt = f".{fmt}"
        try:
            return OutputFormat(fmt)
        except ValueError as exc:
            supported = ", ".join(fmt_.value for fmt_ in OutputFormat)
            raise ValueError(
                f"Unsupported output format {value!r}; supported: {supported}"
            ) from exc

    @staticmethod
    def supported_formats() -> str:
        return ", ".join(fmt_.value for fmt_ in OutputFormat)
