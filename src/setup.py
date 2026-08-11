"""Setup script mapping the 'cru' entry point."""

from __future__ import annotations

from setuptools import setup

setup(
    packages=[
        "cruine",
        "cruine.commands",
        "cruine.config",
        "cruine.core",
        "cruine.models",
        "cruine.utils",
    ],
    package_dir={"cruine": "."},
    entry_points={"console_scripts": ["cru=cruine.cli:main"]},
    zip_safe=False,
)
