cmake_minimum_required(VERSION 3.20)
include(CheckIncludeFile)

get_filename_component(REPO_ROOT "${CMAKE_CURRENT_LIST_DIR}" ABSOLUTE)

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSROOT /)

# ── Host profile detection (Cudane: musl+clang+clang++ /system, else gcc /usr)
execute_process(
  COMMAND "${REPO_ROOT}/scripts/detect.sh" cc
  OUTPUT_VARIABLE CRUINE_CC
  OUTPUT_STRIP_TRAILING_WHITESPACE
)
execute_process(
  COMMAND "${REPO_ROOT}/scripts/detect.sh" cxx
  OUTPUT_VARIABLE CRUINE_CXX
  OUTPUT_STRIP_TRAILING_WHITESPACE
)
execute_process(
  COMMAND "${REPO_ROOT}/scripts/detect.sh" prefix
  OUTPUT_VARIABLE CRUINE_PREFIX
  OUTPUT_STRIP_TRAILING_WHITESPACE
)
execute_process(
  COMMAND "${REPO_ROOT}/scripts/detect.sh" triple
  OUTPUT_VARIABLE CRUINE_TRIPLE
  OUTPUT_STRIP_TRAILING_WHITESPACE
)

# ── Auto-detect host architecture (Cudane ships amd64 and arm64) ────────
execute_process(
  COMMAND uname -m
  OUTPUT_VARIABLE CRUINE_HOST_ARCH
  OUTPUT_STRIP_TRAILING_WHITESPACE
)

if(CRUINE_HOST_ARCH STREQUAL "x86_64")
  set(CMAKE_SYSTEM_PROCESSOR x86_64)
elseif(CRUINE_HOST_ARCH STREQUAL "aarch64")
  set(CMAKE_SYSTEM_PROCESSOR aarch64)
else()
  message(FATAL_ERROR "Unsupported architecture: ${CRUINE_HOST_ARCH}. Supported: x86_64, aarch64")
endif()

# Cruine is a pure-Python project; the standalone binary is produced by
# PyInstaller (single self-contained executable, no system Python needed).
# The detected compiler is retained for any C extension rebuilds.
set(CMAKE_C_COMPILER "${CRUINE_CC}")
set(CMAKE_CXX_COMPILER "${CRUINE_CXX}")
set(CMAKE_C_FLAGS_INIT "-O2")
set(CMAKE_CXX_FLAGS_INIT "-O2")

set(CMAKE_FIND_ROOT_PATH "${CRUINE_PREFIX}")
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
