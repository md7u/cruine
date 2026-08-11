"""Tests for the pydantic data models."""

from __future__ import annotations

from typing import Any

import pytest
from cruine.models.device import DeviceModel, RepositoryModel
from cruine.models.options import OptionsModel
from cruine.models.output import OutputFormat, OutputModel
from cruine.models.recipe import RecipeSchema
from pydantic import ValidationError


def _device(**overrides: Any) -> dict:
    base: dict = {
        "codename": "alioth",
        "repositories": [
            {
                "type": "device",
                "url": "https://example.com/device.git",
                "target_path": "device/xiaomi/alioth",
            }
        ],
    }
    base.update(overrides)
    return base


def _recipe(**overrides: Any) -> dict:
    base: dict = {
        "project_name": "TestROM",
        "rom": {
            "source": "https://example.com/android.git",
            "branch": "lineage-21.0",
            "lunch_prefix": "lineage",
            "build_target": "bacon",
        },
        "device": _device(),
    }
    base.update(overrides)
    return base


def test_output_format_normalization() -> None:
    assert OutputModel(format="tgz").format is OutputFormat.TGZ
    assert OutputModel(format="TAR.GZ").format is OutputFormat.TAR_GZ
    assert OutputModel(format=".zip").format is OutputFormat.ZIP


def test_invalid_output_format_rejected() -> None:
    with pytest.raises(ValidationError):
        OutputModel(format="rar")


def test_ccache_size_validation() -> None:
    assert OptionsModel(ccache_size="4g").ccache_size == "4G"
    with pytest.raises(ValidationError):
        OptionsModel(ccache_size="lots")


def test_build_variant_validation() -> None:
    with pytest.raises(ValidationError):
        OptionsModel(build_variant="release")


def test_parallel_jobs_validation() -> None:
    with pytest.raises(ValidationError):
        OptionsModel(parallel_jobs=0)


def test_repository_type_validation() -> None:
    with pytest.raises(ValidationError):
        RepositoryModel(type="bad", url="https://example.com/x.git", target_path="a/b")


def test_repository_target_path_rejects_whitespace() -> None:
    with pytest.raises(ValidationError):
        RepositoryModel(type="device", url="https://example.com/x.git", target_path="a b/c")


def test_codename_validation() -> None:
    with pytest.raises(ValidationError):
        DeviceModel(**_device(codename="Bad Name"))


def test_device_allows_empty_sources_for_repack() -> None:
    device = DeviceModel(codename="alioth", repositories=[], files=[])
    assert device.repositories == []
    with pytest.raises(ValidationError):
        RecipeSchema.model_validate(_recipe(device={"codename": "alioth"}))
    repack = _recipe(input={"archive": "/tmp/stock.zip"}, device={"codename": "alioth"})
    assert RecipeSchema.model_validate(repack).input.archive == "/tmp/stock.zip"


def test_recipe_round_trip() -> None:
    recipe = RecipeSchema.model_validate(_recipe())
    assert recipe.project_name == "TestROM"
    assert recipe.lunch_combo() == "lineage_alioth-userdebug"
    assert recipe.output.format is OutputFormat.ZIP
