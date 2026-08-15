REPO_ROOT   := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
SYSROOT     := /
PYTHON      ?= python3
VENV        ?= $(REPO_ROOT)/.venv
# Python 3.12+ venvs no longer ship a `pip` script in bin/, so install into
# the venv via the interpreter targeting form instead.
PIP         := $(PYTHON) -m pip --python $(VENV)/bin/python
PY          := $(VENV)/bin/python
PYINSTALLER := $(PY) -m PyInstaller

# ── Host profile detection (Cudane: musl+clang, /system; else glibc+gcc, /usr)
DETECT     := $(REPO_ROOT)/scripts/detect.sh
DISTRO     := $(shell $(DETECT) distro)
LIBC       := $(shell $(DETECT) libc)
ARCH       := $(shell $(DETECT) arch)
PREFIX     ?= $(shell $(DETECT) prefix)
# `:=` (not ?=) so make's built-in CC=cc default does not win; a command-line
# CC=... override still takes precedence.
CC         := $(shell $(DETECT) cc)
CXX        := $(shell $(DETECT) cxx)
TARGET_TRIPLE := $(shell $(DETECT) triple)

export CC
export CXX
export LIBC
export ARCH

# PyInstaller bundles cruine and its third-party dependencies into a single
# standalone executable that needs no system Python. The build delegates to
# scripts/package.sh (packaging/cru.spec collects third-party data/dylibs via
# collect_all).
