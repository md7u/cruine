"""RecipeSchema: root recipe model combining all sub-models."""

from __future__ import annotations

from cruine.models.device import DeviceModel
from cruine.models.input import InputModel
from cruine.models.options import OptionsModel
from cruine.models.output import OutputModel
from cruine.models.patch import HookModel, PatchModel
from cruine.models.rom import ROMModel
from pydantic import BaseModel, Field, model_validator


class RecipeSchema(BaseModel):
    project_name: str
    rom: ROMModel
    device: DeviceModel
    input: InputModel = Field(default_factory=InputModel)
    options: OptionsModel = Field(default_factory=OptionsModel)
    output: OutputModel = Field(default_factory=OutputModel)
    patches: list[PatchModel] = Field(default_factory=list)
    hooks: list[HookModel] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_source(self) -> RecipeSchema:
        if not self.input.archive and not self.device.repositories and not self.device.files:
            raise ValueError(
                "recipe must define at least one 'device.repositories' or "
                "'device.files' entry, or set 'input.archive'"
            )
        return self

    def lunch_combo(self) -> str:
        return f"{self.rom.lunch_prefix}_{self.device.codename}-{self.options.build_variant}"
