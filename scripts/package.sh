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
BUILDVENV="${ROOT}/.venv"
BUILDVENVPY="${BUILDVENV}/bin/python3"

pip_venv() {
    "${PYTHON}" -m pip --python "${BUILDVENVPY}" "$@"
}

if [ ! -x "${BUILDVENVPY}" ]; then
    "${PYTHON}" -m venv "${BUILDVENV}"
    pip_venv install --upgrade pip
    pip_venv install pyinstaller
    pip_venv install "${ROOT}/src"
fi

pip_venv install --force-reinstall --no-deps "${ROOT}/src"

mkdir -p "${DIST}"
"${BUILDVENVPY}" -m PyInstaller --noconfirm \
    --distpath "${DIST}" \
    --workpath "${WORK}" \
    "${ROOT}/packaging/cru.spec"
