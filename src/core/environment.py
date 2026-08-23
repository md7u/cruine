"""System host prerequisites and CCACHE engine."""

from __future__ import annotations

import glob
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from cruine.models.recipe import RecipeSchema
from cruine.utils.logger import log

REQUIRED_TOOLS = ("git", "bash", "tar", "python3", "make", "java", "javac")

# Typical host tools AOSP/Kernel builds pull in. Missing ones are warned
# about but do not block the pipeline (prebuilts cover several of them).
# The compiler set depends on the libc profile: Cudane (musl-libc) uses
# clang/clang++, glibc distributions use gcc/g++.
HOST_BUILD_TOOLS = (
    "curl",
    "rsync",
    "lzip",
    "xz",
    "zstd",
    "lz4",
    "bc",
    "bison",
    "flex",
    "openssl",
    "git-lfs",
    "schedtool",
    "m4",
    "perl",
    "clang",
    "clang++",
    "gcc",
    "g++",
    "ninja",
    "cmake",
)

# Cruine can work around these when absent (native replacements / CLI fallbacks).
OPTIONAL_TOOLS = ("ccache", "7z", "mkisofs", "genisoimage", "xorriso", "unzip")


@dataclass
class ToolReport:
    present: dict[str, str] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)


@dataclass
class JavaReport:
    java: str | None
    javac: str | None
    version: str | None
    major: int | None

    @property
    def is_jdk(self) -> bool:
        return self.javac is not None

    @property
    def aosp_hint(self) -> str | None:
        if self.major == 17:
            return "JDK 17 (Android 14+/13+)"
        if self.major == 11:
            return "JDK 11 (Android 11-12)"
        if self.major == 8:
            return "JDK 8 (Android 10 and earlier)"
        if self.major is not None:
            return f"JDK {self.major} is unusual for AOSP; 8/11/17 are the usual targets"
        return None


@dataclass
class EnvironmentReport:
    tools: ToolReport
    python_version: str
    total_memory_gb: float
    cpu_cores: int
    recommended_jobs: int
    ccache_dir: Path
    java: JavaReport
    libc: str
    arch: str
    target_triple: str
    cc: str
    cxx: str
    missing_required: list[str]
    missing_build_tools: list[str]
    missing_optional: list[str]

    @property
    def ready(self) -> bool:
        return not self.missing_required


class EnvironmentManager:
    """Verifies host prerequisites and prepares the build environment."""

    def __init__(self) -> None:
        self.ccache_dir = Path(os.environ.get("CCACHE_DIR") or (Path.home() / ".cache" / "ccache"))

    def check_tools(self) -> ToolReport:
        report = ToolReport()
        for tool in REQUIRED_TOOLS + HOST_BUILD_TOOLS + OPTIONAL_TOOLS:
            path = shutil.which(tool)
            if path:
                report.present[tool] = path
            else:
                report.missing.append(tool)
        return report

    def check_java(self) -> JavaReport:
        java = shutil.which("java")
        javac = shutil.which("javac")
        version, major = self._java_version(java) if java else (None, None)
        return JavaReport(java=java, javac=javac, version=version, major=major)

    @staticmethod
    def _java_version(java_bin: str) -> tuple[str | None, int | None]:
        try:
            proc = subprocess.run(
                [java_bin, "-version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None, None
        text = (proc.stderr or "") + (proc.stdout or "")
        match = re.search(r'version "([^"]+)"', text)
        if not match:
            return None, None
        version = match.group(1)
        major_match = re.match(r"1\.(\d+)", version) or re.match(r"(\d+)\.?", version)
        major = int(major_match.group(1)) if major_match else None
        return version, major

    @staticmethod
    def detect_libc() -> str:
        """Return ``musl`` (Cudane) or ``glibc``.

        A musl loader anywhere under /lib is authoritative; otherwise ldd's
        banner distinguishes the two. A CRUINE_LIBC override forces a profile
        (useful when cross-building Cudane from a glibc host).
        """
        override = os.environ.get("CRUINE_LIBC")
        if override in ("musl", "glibc"):
            return override
        for pattern in ("/lib/ld-musl-*.so.1", "/lib/*/ld-musl-*.so.1"):
            if glob.glob(pattern):
                return "musl"
        try:
            ldd = subprocess.run(
                ["ldd", "--version"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if "musl" in (ldd.stdout + ldd.stderr).lower():
                return "musl"
        except (OSError, subprocess.SubprocessError):
            pass
        return "glibc"

    @staticmethod
    def detect_arch() -> str:
        machine = platform.machine().lower()
        if machine in ("x86_64", "amd64"):
            return "amd64"
        if machine in ("aarch64", "arm64"):
            return "arm64"
        return machine

    @staticmethod
    def toolchain_for(libc: str) -> tuple[str, str]:
        if libc == "musl":
            return "clang", "clang++"
        return "gcc", "g++"

    @staticmethod
    def target_triple_for(libc: str, arch: str) -> str:
        cpu = {"amd64": "x86_64", "arm64": "aarch64"}.get(arch, arch)
        env = "musl" if libc == "musl" else "gnu"
        return f"{cpu}-unknown-linux-{env}"

    def inspect_host(self) -> EnvironmentReport:
        tools = self.check_tools()
        total_gb = self._total_memory_bytes() / (1024**3)
        cores = os.cpu_count() or 1
        recommended = max(1, min(cores, 16))
        libc = self.detect_libc()
        arch = self.detect_arch()
        cc, cxx = self.toolchain_for(libc)
        return EnvironmentReport(
            tools=tools,
            python_version=sys.version.split()[0],
            total_memory_gb=round(total_gb, 1),
            cpu_cores=cores,
            recommended_jobs=recommended,
            ccache_dir=self.ccache_dir,
            java=self.check_java(),
            libc=libc,
            arch=arch,
            target_triple=self.target_triple_for(libc, arch),
            cc=cc,
            cxx=cxx,
            missing_required=[t for t in REQUIRED_TOOLS if t in tools.missing],
            missing_build_tools=[t for t in HOST_BUILD_TOOLS if t in tools.missing],
            missing_optional=[t for t in OPTIONAL_TOOLS if t in tools.missing],
        )

    @staticmethod
    def _total_memory_bytes() -> int:
        try:
            with open("/proc/meminfo", encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("MemTotal:"):
                        return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            pass
        return 0

    def validate(self) -> EnvironmentReport:
        report = self.inspect_host()
        log.info(
            f"Host: Python {report.python_version} | {report.cpu_cores} cores | "
            f"{report.total_memory_gb} GB RAM | recommended -j{report.recommended_jobs}"
        )
        if report.tools.present:
            found = ", ".join(
                f"{name}={path}" for name, path in sorted(report.tools.present.items())
            )
            log.info(f"Tools found: {found}")
        if report.java.java:
            log.info(f"Java: {report.java.version or 'unknown version'} at {report.java.java}")
            if not report.java.is_jdk:
                log.critical(
                    "javac not found - AOSP requires a full JDK, not a bare JRE. "
                    "Install one, e.g.: sudo pacman -S jdk17-openjdk (Arch) or "
                    "sudo apt install openjdk-17-jdk (Debian/Ubuntu)"
                )
                return report
            if report.java.aosp_hint and report.java.major not in (8, 11, 17):
                log.warning(report.java.aosp_hint)
        elif "java" in report.missing_required:
            log.critical(
                "No Java runtime found - AOSP requires a JDK to build. "
                "Install one, e.g.: sudo pacman -S jdk17-openjdk (Arch) or "
                "sudo apt install openjdk-17-jdk (Debian/Ubuntu)"
            )
            return report
        if report.missing_required:
            log.critical(
                "Missing required tools: "
                + ", ".join(report.missing_required)
                + ". Install them first, e.g.: sudo apt install git python3 bash tar "
                "make openjdk-17-jdk"
            )
            return report
        if report.missing_build_tools:
            log.warning(
                "Host build tools missing (AOSP/Kernel builds may need them; "
                "some are provided as prebuilts): " + ", ".join(report.missing_build_tools)
            )
        if report.missing_optional:
            log.warning(
                "Optional tools missing (fallbacks will be used if possible): "
                + ", ".join(report.missing_optional)
            )
        return report

    def setup_ccache(self, recipe: RecipeSchema) -> None:
        if not recipe.options.use_ccache:
            log.info("CCACHE disabled by recipe (options.use_ccache=false)")
            return
        ccache_bin = shutil.which("ccache")
        if not ccache_bin:
            log.warning("ccache binary not found; continuing without ccache")
            return
        self.ccache_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [ccache_bin, "-M", recipe.options.ccache_size],
                check=True,
                capture_output=True,
                text=True,
                env={**os.environ, "CCACHE_DIR": str(self.ccache_dir)},
            )
            log.success(f"ccache configured: {recipe.options.ccache_size} -> {self.ccache_dir}")
        except subprocess.CalledProcessError as exc:
            log.warning(f"Could not set ccache max size: {(exc.stderr or '').strip() or exc}")

    def build_environment(self, recipe: RecipeSchema, jobs: int) -> dict[str, str]:
        env = os.environ.copy()
        if recipe.options.use_ccache:
            env["USE_CCACHE"] = "1"
            ccache_bin = shutil.which("ccache")
            if ccache_bin:
                env["CCACHE_EXEC"] = ccache_bin
            env["CCACHE_DIR"] = str(self.ccache_dir)
        env["LC_ALL"] = "C"
        env["LANG"] = "C"
        env["CRU_JOBS"] = str(jobs)
        return env

    def check_disk_space(self, path: Path, min_gb: float) -> tuple[bool, float]:
        try:
            usage = shutil.disk_usage(path)
        except OSError:
            return True, 0.0
        free_gb = usage.free / (1024**3)
        return free_gb >= min_gb, free_gb

    @staticmethod
    def recommended_memory_limit_mb(min_free_gb: int = 8) -> int | None:
        total_mb = EnvironmentManager._total_memory_bytes() // (1024**2)
        if total_mb <= 0:
            return None
        limit = total_mb - min_free_gb * 1024
        return limit if limit > 0 else None

    @staticmethod
    def ulimit_prefix(limit_mb: int) -> str:
        return f"ulimit -v {limit_mb * 1024}; "
