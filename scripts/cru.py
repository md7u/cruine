"""Standalone entry point: bundled by PyInstaller into the `cru` binary.

Running this module directly (python scripts/cru.py) requires the cruine
package to be importable; the PyInstaller build bundles everything into one
self-contained executable that needs no system Python.
"""

from __future__ import annotations

from cruine.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
