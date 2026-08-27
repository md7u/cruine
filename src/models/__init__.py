"""Cruine data models."""

from __future__ import annotations

from cruine.models.device import DeviceModel, LocalFileModel, RepositoryModel
from cruine.models.input import SUPPORTED_INPUT_FORMATS, InputModel
from cruine.models.options import OptionsModel
from cruine.models.output import OutputFormat, OutputModel
from cruine.models.patch import HookModel, PatchModel
from cruine.models.recipe import RecipeSchema
from cruine.models.rom import ROMModel

__all__ = [
    "SUPPORTED_INPUT_FORMATS",
    "DeviceModel",
    "HookModel",
    "InputModel",
    "LocalFileModel",
    "OptionsModel",
    "OutputFormat",
    "OutputModel",
    "PatchModel",
    "ROMModel",
    "RecipeSchema",
    "RepositoryModel",
]
