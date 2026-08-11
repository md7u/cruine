#!/bin/bash
# scripts/pkgconfig.sh — pkg-config wrapper that targets the detected install prefix.
#   * Cudane (musl-libc)   -> /system/lib/pkgconfig
#   * glibc GNU/Linux       -> /usr/lib/pkgconfig
# Usage: PKG_CONFIG_PATH=... scripts/pkgconfig.sh [pkg-config args]
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="$("${DIR}/detect.sh" prefix)"
export PKG_CONFIG_SYSROOT_DIR="${CRUINE_SYSROOT:-/}"
export PKG_CONFIG_LIBDIR="${PREFIX}/lib/pkgconfig"
exec pkg-config "$@"
