#!/bin/sh
# package.sh — Build the standalone `cru` binary (PyInstaller).
#
# PyInstaller cannot follow PEP 660 editable installs, so cruine is installed
# as a regular (non-editable) package into a scratch build venv before the
# spec runs. All build files (Makefile, build.ninja, meson.build) delegate to
# this script so the artifact is identical everywhere.
#
# Usage: scripts/package.sh [dist-dir] [work-dir]
#   dist-dir  where the final `cru` binary is written (default: builddir)
#   work-dir  PyInstaller work/spec scratch (default: <dist-dir>/cru-build)
set -e

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
DIST="${1:-${ROOT}/builddir}"
WORK="${2:-${DIST}/cru-build}"
PYTHON="${PYTHON:-python3}"
BUILDVENV="${ROOT}/target/cru-buildvenv"
BUILDVENVPY="${BUILDVENV}/bin/python"
BUILDVENVPIP="${BUILDVENV}/bin/pip"

if [ ! -x "${BUILDVENVPY}" ]; then
    "${PYTHON}" -m venv "${BUILDVENV}"
    "${BUILDVENVPIP}" install --upgrade pip
    "${BUILDVENVPIP}" install pyinstaller
    "${BUILDVENVPIP}" install "${ROOT}/src"
fi

"${BUILDVENVPIP}" install --force-reinstall --no-deps "${ROOT}/src"

mkdir -p "${DIST}"
"${BUILDVENVPY}" -m PyInstaller --noconfirm \
    --distpath "${DIST}" \
    --workpath "${WORK}" \
    "${ROOT}/packaging/cru.spec"
