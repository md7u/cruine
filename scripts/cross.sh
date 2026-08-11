#!/bin/sh
# scripts/cross.sh — Generate a Meson cross-file for Cruine.
# Detects the host profile via scripts/detect.sh:
#   * Cudane (musl-libc)      -> clang/clang++, x86_64|aarch64-unknown-linux-musl, /system
#   * glibc GNU/Linux          -> gcc/g++, x86_64|aarch64-unknown-linux-gnu, /usr
# Usage: ./scripts/cross.sh [output_path]
set -e

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DETECT="${SCRIPT_DIR}/detect.sh"
OUT="${1:-${SCRIPT_DIR}/cross.txt}"
SYSROOT="${CRUINE_SYSROOT:-/}"
# Join paths without doubling the slash when SYSROOT is "/".
SYSROOT_PATH="${SYSROOT%/}"

LIBC=$("${DETECT}" libc)
ARCH=$("${DETECT}" arch)
PREFIX=$("${DETECT}" prefix)
CC=$("${DETECT}" cc)
CXX=$("${DETECT}" cxx)
TRIPLE=$("${DETECT}" triple)

case "${LIBC}" in
  musl|glibc) ;;
  *) echo "error: unknown libc '${LIBC}'" >&2; exit 1 ;;
esac

# clang takes -target <triple>; gcc compiles natively without it.
if [ "${CC}" = clang ]; then
  CC_ARGS="'-target', '${TRIPLE}', '-O2'"
  LINK_ARGS="'-target', '${TRIPLE}', '-L${SYSROOT_PATH}${PREFIX}/lib'"
else
  CC_ARGS="'-O2'"
  LINK_ARGS="'-L${SYSROOT_PATH}${PREFIX}/lib'"
fi

cat > "$OUT" <<EOF
[binaries]
c = '${CC}'
cpp = '${CXX}'
rust = 'rustc'
pkg-config = '${SCRIPT_DIR}/pkgconfig.sh'

[properties]
sys_root = '${SYSROOT}'

[built-in options]
c_args = [${CC_ARGS}, '-I${SYSROOT_PATH}${PREFIX}/include']
cpp_args = [${CC_ARGS}, '-I${SYSROOT_PATH}${PREFIX}/include']
c_link_args = [${LINK_ARGS}]
cpp_link_args = [${LINK_ARGS}]

[host_machine]
system = 'linux'
cpu_family = '${TRIPLE%%-*}'
cpu = '${TRIPLE%%-*}'
endian = 'little'
EOF

echo "cross.txt generated for ${TRIPLE} (${CC}/${LIBC}, prefix ${PREFIX}) → ${OUT}"
