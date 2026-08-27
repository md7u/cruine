"""RecipeSchema: root recipe model combining all sub-models."""

from __future__ import annotations

import dataclasses

from cruine.models.base import BaseModel
from cruine.models.device import DeviceModel
from cruine.models.input import InputModel
from cruine.models.options import OptionsModel
from cruine.models.output import OutputModel
from cruine.models.patch import HookModel, PatchModel
from cruine.models.rom import ROMModel


def _model_validator(fn):
    fn._is_model_validator = True
    return fn


@dataclasses.dataclass
class RecipeSchema(BaseModel):
    project_name: str = ""
    rom: ROMModel = dataclasses.field(default_factory=ROMModel)
    device: DeviceModel = dataclasses.field(default_factory=DeviceModel)
    input: InputModel = dataclasses.field(default_factory=InputModel)
    options: OptionsModel = dataclasses.field(default_factory=OptionsModel)
    output: OutputModel = dataclasses.field(default_factory=OutputModel)
    patches: list[PatchModel] = dataclasses.field(default_factory=list)
    hooks: list[HookModel] = dataclasses.field(default_factory=list)

    @_model_validator
    def _require_source(self) -> None:
        if not self.input.archive and not self.device.repositories and not self.device.files:
            raise ValueError(
                "recipe must define at least one 'device.repositories' or "
                "'device.files' entry, or set 'input.archive'"
            )

    def lunch_combo(self) -> str:
        return f"{self.rom.lunch_prefix}_{self.device.codename}-{self.options.build_variant}"
