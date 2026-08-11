"""Tests for recipe discovery and loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cruine.config.loader import EXAMPLE_RECIPE, RecipeLoader


def test_write_template(tmp_path: Path) -> None:
    target = RecipeLoader.write_template(tmp_path / "rc.json")
    assert target.is_file()
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["project_name"] == EXAMPLE_RECIPE["project_name"]


def test_write_template_refuses_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "rc.json"
    target.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        RecipeLoader.write_template(target)


def test_load_from_path(recipe_file: Path) -> None:
    recipe = RecipeLoader().load_from_path(recipe_file)
    assert recipe.project_name == "TestROM"
    assert recipe.lunch_combo() == "test_testdevice-userdebug"


def test_load_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "rc.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError):
        RecipeLoader().load_from_path(path)


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        RecipeLoader().load_from_path(tmp_path / "nope.json")


def test_auto_discover_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        RecipeLoader().auto_discover_and_load()


def test_auto_discover_finds_recipe(recipe_file: Path, monkeypatch) -> None:
    monkeypatch.chdir(recipe_file.parent)
    recipe = RecipeLoader().auto_discover_and_load()
    assert recipe.project_name == "TestROM"
