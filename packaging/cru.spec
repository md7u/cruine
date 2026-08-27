"""PyInstaller spec for the standalone `cru` binary.

`cruine` is installed as a normal (non-editable) wheel into a scratch build
venv by `make build`, so PyInstaller resolves it from site-packages without
the PEP 660 editable-install incompatibility. `cruine` has no third-party
runtime dependencies, so there is nothing to collect via `collect_all`.
"""

from __future__ import annotations

import os

_SPEC_DIR = os.path.dirname(os.path.abspath(SPEC))
_ROOT = os.path.dirname(_SPEC_DIR)

from PyInstaller.building.build_main import EXE, PYZ, Analysis

_all_datas: list = []
_all_binaries: list = []
_all_hidden: list = []

# `cruine` has no third-party runtime dependencies (pure stdlib), so there
# are no external packages to collect via `collect_all`.

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
