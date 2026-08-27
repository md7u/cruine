"""Minimal BaseModel base class using stdlib dataclasses."""

from __future__ import annotations

import dataclasses
from typing import Any, get_type_hints


class ValidationError(ValueError):
    """Raised when model validation fails."""

    def __init__(self, errors: list[dict[str, Any]]) -> None:
        self._errors = errors
        msg = "Validation failed:\n" + "\n".join(
            f"  - {e.get('loc', '<root>')}: {e.get('msg', '?')}" for e in errors
        )
        super().__init__(msg)

    def errors(self) -> list[dict[str, Any]]:
        return list(self._errors)


def _collect_validators(cls: type) -> dict[str, list[tuple[str, Any]]]:
    """Walk the MRO and collect field validators (methods with _field_name attr)."""
    validators: dict[str, list[tuple[str, Any]]] = {}
    for klass in reversed(cls.__mro__):
        for attr_name, attr in klass.__dict__.items():
            if isinstance(attr, staticmethod):
                func = attr.__func__
                if hasattr(func, "_field_name"):
                    field_name = func._field_name
                    validators.setdefault(field_name, [])
                    if not any(name == attr_name for name, _ in validators[field_name]):
                        validators[field_name].append((attr_name, func))
            elif callable(attr) and hasattr(attr, "_field_name"):
                field_name = attr._field_name
                validators.setdefault(field_name, [])
                if not any(name == attr_name for name, _ in validators[field_name]):
                    validators[field_name].append((attr_name, attr))
    return validators


class BaseModel:
    """Minimal base class replacing pydantic.BaseModel."""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Any:
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")
        return cls(**data)

    def __post_init__(self) -> None:
        hints = get_type_hints(type(self))
        for f in dataclasses.fields(self):
            val = getattr(self, f.name)
            if val is None or isinstance(val, str | int | float | bool | bytes):
                continue
            target = hints.get(f.name)
            if target is None:
                continue
            origin = getattr(target, "__origin__", None)
            if origin is list:
                args = getattr(target, "__args__", ())
                if args and isinstance(val, list):
                    inner = args[0]
                    if dataclasses.is_dataclass(inner) and isinstance(inner, type):
                        new_val = []
                        for item in val:
                            if isinstance(item, dict):
                                new_val.append(inner(**item))
                            else:
                                new_val.append(item)
                        setattr(self, f.name, new_val)
            elif (
                dataclasses.is_dataclass(target)
                and isinstance(target, type)
                and isinstance(val, dict)
            ):
                setattr(self, f.name, target(**val))

        validators = _collect_validators(type(self))
        for f in dataclasses.fields(self):
            if f.name in validators:
                for validator in validators[f.name]:
                    try:
                        value = validator[1](getattr(self, f.name))
                    except ValueError as exc:
                        raise ValidationError(
                            [{"loc": f.name, "msg": str(exc), "type": "value_error"}]
                        ) from exc
                    object.__setattr__(self, f.name, value)

        for klass in reversed(type(self).__mro__):
            for attr in klass.__dict__.values():
                if callable(attr) and getattr(attr, "_is_model_validator", False):
                    try:
                        attr(self)
                    except ValueError as exc:
                        raise ValidationError(
                            [{"loc": "<model>", "msg": str(exc), "type": "value_error"}]
                        ) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        object.__setattr__(self, name, value)
        try:
            validators = _collect_validators(type(self))
        except Exception:
            return
        if name in validators:
            for validator in validators[name]:
                try:
                    object.__setattr__(self, name, validator[1](value))
                except ValueError as exc:
                    raise ValidationError(
                        [{"loc": name, "msg": str(exc), "type": "value_error"}]
                    ) from exc

    def model_dump(self) -> dict[str, Any]:
        result = {}
        for f in dataclasses.fields(self):
            val = getattr(self, f.name)
            if dataclasses.is_dataclass(type(val)) and isinstance(val, BaseModel):
                result[f.name] = val.model_dump()
            elif isinstance(val, list):
                new_list = []
                for v in val:
                    if dataclasses.is_dataclass(type(v)) and isinstance(v, BaseModel):
                        new_list.append(v.model_dump())
                    else:
                        new_list.append(v)
                result[f.name] = new_list
            else:
                result[f.name] = val
        return result
