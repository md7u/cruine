"""Schema validation models."""

from __future__ import annotations

from typing import Any

from cruine.models.base import ValidationError
from cruine.models.output import OutputFormat
from cruine.models.recipe import RecipeSchema


class RecipeValidator:
    """Validates raw recipe dictionaries against the schema."""

    @classmethod
    def validate_dict(cls, data: dict[str, Any]) -> RecipeSchema:
        if not isinstance(data, dict):
            raise TypeError("Recipe root must be a JSON object")
        try:
            return RecipeSchema.from_dict(data)
        except ValidationError as exc:
            details = []
            for error in exc.errors():
                location = error.get("loc", "<root>")
                fmt = error.get("type", "?")
                details.append(
                    f"  - {location}: {error.get('msg', '?')} (type={fmt})"
                )
            raise ValueError(
                "rc.json failed schema validation:\n" + "\n".join(details)
            ) from exc

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
