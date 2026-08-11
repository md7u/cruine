"""End-to-end repack tests: input archive -> extract -> hooks/patches -> package."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from cruine.cli import PipelineOptions, run_pipeline, run_repack
from cruine.models.input import InputModel
from cruine.models.recipe import RecipeSchema
from pydantic import ValidationError


def _make_rom_zip(path: Path) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("system/app/Foo/Foo.apk", "apk")
        zf.writestr("build.prop", "ro.product.name=stock\n")
    return path


def _repack_recipe(archive: str, **overrides) -> dict:
    recipe = {
        "project_name": "TestROM",
        "rom": {
            "source": "https://example.com/android.git",
            "branch": "b",
            "lunch_prefix": "test",
            "build_target": "bacon",
        },
        "device": {
            "codename": "testdev",
            "repositories": [
                {"type": "device", "url": "https://e.com/d.git", "target_path": "device/x/a"}
            ],
        },
        "input": {"archive": archive},
        "options": {"use_ccache": False},
        "output": {"format": ".zip"},
    }
    recipe.update(overrides)
    return recipe


def test_input_model_validation() -> None:
    assert InputModel(archive="x.zip").format is None
    assert InputModel(archive="x", format="tar.gz").format == ".tar.gz"
    with pytest.raises(ValidationError):
        InputModel(archive="x", format="rar")


def test_recipe_accepts_input() -> None:
    recipe = RecipeSchema.model_validate(_repack_recipe("rom.zip"))
    assert recipe.input.archive == "rom.zip"


def test_run_pipeline_repack_mode(tmp_path: Path, monkeypatch) -> None:
    archive = _make_rom_zip(tmp_path / "stock.zip")
    recipe = _repack_recipe(
        str(archive),
        hooks=[
            {
                "name": "tweak",
                "command": (
                    "mkdir -p out/target/product/testdev && "
                    "echo modified > out/target/product/testdev/modified.txt"
                ),
                "phase": "post_build",
            }
        ],
    )
    (tmp_path / "rc.json").write_text(json.dumps(recipe), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    destination = tmp_path / "out"
    assert run_pipeline(PipelineOptions(destination=destination)) == 0

    result = destination / "TestROM-testdev.zip"
    assert result.is_file()
    with zipfile.ZipFile(result) as zf:
        names = set(zf.namelist())
        assert "system/app/Foo/Foo.apk" in names
        assert "build.prop" in names
        assert "modified.txt" in names


def test_run_pipeline_repack_runs_pre_fetch_hook(tmp_path: Path, monkeypatch) -> None:
    archive = _make_rom_zip(tmp_path / "stock.zip")
    recipe = _repack_recipe(
        str(archive),
        hooks=[
            {
                "name": "prep",
                "command": "echo ready > pre-fetch-ran.txt",
                "phase": "pre_fetch",
            }
        ],
    )
    (tmp_path / "rc.json").write_text(json.dumps(recipe), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert run_pipeline(PipelineOptions(destination=tmp_path / "out")) == 0
    workspace = tmp_path / "TestROM"
    assert (workspace / "pre-fetch-ran.txt").read_text(encoding="utf-8").strip() == "ready"


def test_run_repack_override_archive_and_format(tmp_path: Path, monkeypatch) -> None:
    archive = _make_rom_zip(tmp_path / "stock.zip")
    recipe = _repack_recipe(str(tmp_path / "unused.zip"))
    (tmp_path / "rc.json").write_text(json.dumps(recipe), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    destination = tmp_path / "out"
    opts = PipelineOptions(destination=destination, dry_run=True)
    assert run_repack(opts, archive=str(archive)) == 0
    assert not destination.exists() or not any(destination.iterdir())

    opts = PipelineOptions(destination=destination, recipe=tmp_path / "rc.json")
    assert run_repack(opts, archive=str(archive), output_format=".tar.gz") == 0
    assert (destination / "TestROM-testdev.tar.gz").is_file()
