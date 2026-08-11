"""PyInstaller spec for the standalone `cru` binary.

`cruine` is installed as a normal (non-editable) wheel into a scratch build
venv by `make build`, so PyInstaller resolves it from site-packages without
the PEP 660 editable-install incompatibility. Third-party packages that ship
data files / native binaries are collected via `collect_all`.
"""

from __future__ import annotations

import os

_SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
_ROOT = os.path.dirname(_SPEC_DIR)

from PyInstaller.building.build_main import EXE, PYZ, Analysis
from PyInstaller.utils.hooks import collect_all  # noqa: E402

_all_datas: list = []
_all_binaries: list = []
_all_hidden: list = []

for package in ("pydantic", "py7zr", "pycdlib"):
    datas, binaries, hidden = collect_all(package)
    _all_datas += datas
    _all_binaries += binaries
    _all_hidden += hidden

a = Analysis(
    [os.path.join(_ROOT, "scripts", "cru.py")],
    pathex=[],
    binaries=_all_binaries,
    datas=_all_datas,
    hiddenimports=_all_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="cru",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
