#!/bin/sh
# scripts/detect.sh — Detect the host distribution, libc, toolchain and install
# prefix used by all of Cruine's build files (Make, Ninja, Meson, CMake).
#
# Cruine supports two host profiles:
#   * Cudane   — musl-libc, LLVM/clang, installs under /system (amd64+arm64)
#   * glibc    — glibc, GCC, installs under /usr (standard GNU/Linux distros)
#
# Usage:
#   ./scripts/detect.sh            print all key=value pairs
#   ./scripts/detect.sh <key>      print a single value
#
# Keys: distro libc prefix cc cxx arch triple
#
# Overrides (environment):
#   CRUINE_PREFIX   force the install prefix
#   CC / CXX        force the compiler pair
set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

detect_libc() {
    # A musl loader present anywhere is authoritative (musl is not dlopen-able
    # through glibc). glibc systems expose ldd --version; Alpine/Cudane do not.
    if ls /lib/ld-musl-*.so.1 >/dev/null 2>&1 \
        || ls /lib/*/ld-musl-*.so.1 >/dev/null 2>&1; then
        echo musl
    elif command -v ldd >/dev/null 2>&1 && ldd --version 2>&1 | grep -qi musl; then
        echo musl
    else
        echo glibc
    fi
}

detect_distro() {
    if [ -r /etc/os-release ]; then
        ID=$(sed -n 's/^ID=//p' /etc/os-release | tr -d '"')
        echo "${ID:-unknown}"
    elif command -v lsb_release >/dev/null 2>&1; then
        lsb_release -si | tr '[:upper:]' '[:lower:]'
    else
        echo unknown
    fi
}

detect_arch() {
    case $(uname -m) in
        x86_64) echo amd64 ;;
        aarch64) echo arm64 ;;
        *) echo "error: unsupported architecture: $(uname -m)" >&2; exit 1 ;;
    esac
}

# --- base detection -------------------------------------------------------
LIBC=$(detect_libc)
DISTRO=$(detect_distro)
ARCH=$(detect_arch)

# CRUINE_LIBC forces the profile (e.g. cross-building Cudane from a glibc box).
LIBC=${CRUINE_LIBC:-${LIBC}}

# Cudane = musl-libc system. The os-release ID may be "cudane"; a musl libc is
# sufficient evidence on its own.
if [ "${DISTRO}" = cudane ] || [ "${LIBC}" = musl ]; then
    IS_CUDANE=1
else
    IS_CUDANE=0
fi

# --- derived values -------------------------------------------------------
PREFIX=${CRUINE_PREFIX:-}
if [ -z "${PREFIX}" ]; then
    if [ "${IS_CUDANE}" = 1 ]; then
        PREFIX=/system
    else
        PREFIX=/usr
    fi
fi

if [ "${IS_CUDANE}" = 1 ]; then
    CC=${CC:-clang}
    CXX=${CXX:-clang++}
else
    CC=${CC:-gcc}
    CXX=${CXX:-g++}
fi

# Canonical Rust-style target triples (Cudane builds amd64 and arm64).
case "${ARCH}" in
    amd64) TRIPLE_CPU=x86_64 ;;
    arm64) TRIPLE_CPU=aarch64 ;;
esac
case "${LIBC}" in
    musl) TRIPLE_ENV=musl ;;
    glibc) TRIPLE_ENV=gnu ;;
    *) TRIPLE_ENV="${LIBC}" ;;
esac
TRIPLE="${TRIPLE_CPU}-unknown-linux-${TRIPLE_ENV}"

# --- output ---------------------------------------------------------------
if [ "${1:-}" ]; then
    case "$1" in
        distro) echo "${DISTRO}" ;;
        libc) echo "${LIBC}" ;;
        prefix) echo "${PREFIX}" ;;
        cc) echo "${CC}" ;;
        cxx) echo "${CXX}" ;;
        arch) echo "${ARCH}" ;;
        triple) echo "${TRIPLE}" ;;
        *)
            echo "error: unknown key '$1' (distro|libc|prefix|cc|cxx|arch|triple)" >&2
            exit 1
            ;;
    esac
else
    echo "distro=${DISTRO}"
    echo "libc=${LIBC}"
    echo "arch=${ARCH}"
    echo "prefix=${PREFIX}"
    echo "cc=${CC}"
    echo "cxx=${CXX}"
    echo "triple=${TRIPLE}"
fi
