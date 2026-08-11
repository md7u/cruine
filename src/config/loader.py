"""Automatic discovery and JSON parsing logic."""

from __future__ import annotations

import json
from pathlib import Path

from cruine.config.validator import RecipeValidator
from cruine.models.recipe import RecipeSchema
from cruine.utils.logger import log

DEFAULT_RECIPE_NAME = "rc.json"

EXAMPLE_RECIPE = {
    "project_name": "LineageOS-PocoF3",
    "rom": {
        "source": "https://github.com/LineageOS/android.git",
        "branch": "lineage-21.0",
        "lunch_prefix": "lineage",
        "build_target": "bacon",
    },
    "device": {
        "codename": "alioth",
        "repositories": [
            {
                "type": "device",
                "url": "https://github.com/LineageOS/android_device_xiaomi_alioth.git",
                "target_path": "device/xiaomi/alioth",
            },
            {
                "type": "kernel",
                "url": "https://github.com/LineageOS/android_kernel_xiaomi_alioth.git",
                "target_path": "kernel/xiaomi/alioth",
            },
            {
                "type": "vendor",
                "url": "https://github.com/TheMuppets/manifest_xiaomi_alioth.git",
                "target_path": "vendor/xiaomi/alioth",
            },
        ],
    },
    "options": {
        "use_ccache": True,
        "ccache_size": "50G",
        "clean_build": False,
    },
    "output": {
        "format": ".tar.gz",
        "custom_name": "LineageOS-21.0-alioth-UNOFFICIAL",
        "compression_level": 9,
    },
}


class RecipeLoader:
    """Discovers and parses rc.json recipe files."""

    def __init__(self, validator: RecipeValidator | None = None) -> None:
        self.validator = validator or RecipeValidator()

    def auto_discover_and_load(self, search_dir: Path | None = None) -> RecipeSchema:
        search_dir = Path(search_dir) if search_dir is not None else Path.cwd()
        search_dir = search_dir.resolve()
        recipe_path = search_dir / DEFAULT_RECIPE_NAME
        if not recipe_path.is_file():
            raise FileNotFoundError(
                f"rc.json not found in {search_dir}.\n"
                "Run cru from a directory containing an rc.json recipe, or pass "
                "--recipe/-r <path> to point at a recipe elsewhere."
            )
        log.info(f"Discovered recipe: {recipe_path}")
        return self.load_from_path(recipe_path)

    def load_from_path(self, path: Path) -> RecipeSchema:
        path = Path(path)
        if not path.is_file():
            raise FileNotFoundError(f"Recipe file does not exist: {path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
        return self.validator.validate_dict(raw)

    @staticmethod
    def write_template(target: Path) -> Path:
        target = Path(target)
        if target.is_dir():
            target = target / DEFAULT_RECIPE_NAME
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite existing recipe: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(EXAMPLE_RECIPE, indent=2) + "\n", encoding="utf-8")
        return target
