"""Package entry point: python -m cruine."""

from __future__ import annotations

import sys

try:
    from cruine.cli import main
except ImportError:  # pragma: no cover - running directly from the source tree
    from cli import main  # type: ignore


if __name__ == "__main__":
    sys.exit(main())
