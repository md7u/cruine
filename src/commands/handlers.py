"""Command handlers and the handler registry."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from cruine.commands.model import Resolution
from cruine.commands.tree import TREE, _find_by_path, _full_path, _print_node, _print_tree

if TYPE_CHECKING:
    from cruine.models.recipe import RecipeSchema

__all__ = ["HANDLERS"]


def _load_recipe(res: Resolution) -> RecipeSchema:
    from cruine.config.loader import RecipeLoader

    loader = RecipeLoader()
    if res.flag("recipe"):
        return loader.load_from_path(Path(res.flag("recipe")))
    return loader.auto_discover_and_load()


def _workspace(res: Resolution) -> Path:
    if res.flag("path"):
        return Path(res.flag("path"))
    return Path.cwd() / _load_recipe(res).project_name


def _int_flag(res: Resolution, name: str) -> int | None:
    value = res.flag(name)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _h_echo(res: Resolution) -> int:
    print("command  :", " ".join(res.path))
    for key, value in res.flags.items():
        print(f"  {key} = {value}")
    if res.values:
        print("  args   :", " ".join(res.values))
    return 0


def _h_describe(res: Resolution) -> int:
    assert res.node is not None
    _print_node(res.node, res.path)
    return 0


def _h_version(res: Resolution) -> int:
    from cruine import __version__

    print(f"Cruine {__version__}")
    return 0


def _h_formats(res: Resolution) -> int:
    from cruine.models.output import OutputFormat

    for fmt in OutputFormat:
        print(fmt.value)
    return 0


def _h_init(res: Resolution) -> int:
    from cruine.config.loader import RecipeLoader

    target = (
        res.values[0] if res.values else str(res.flag("output") or res.flag("path") or "rc.json")
    )
    path = RecipeLoader.write_template(Path(target))
    print(f"Example rc.json written to: {path}")
    return 0


def _h_doctor(res: Resolution) -> int:
    from cruine.core.environment import EnvironmentManager

    report = EnvironmentManager().validate()
    if not report.ready:
        print(
            "environment validation FAILED; missing: " + ", ".join(report.missing_required),
            file=sys.stderr,
        )
        return 1
    print("environment OK: " + ", ".join(sorted(report.tools.present)))
    print(f"libc         : {report.libc} ({report.arch}, {report.target_triple})")
    print(f"compiler     : {report.cc} / {report.cxx}")
    if report.java.java:
        jdk = "yes" if report.java.is_jdk else "no"
        version = report.java.version or "unknown version"
        print(f"java         : {version} (JDK: {jdk})")
    if report.missing_build_tools:
        print("build tools missing: " + ", ".join(report.missing_build_tools))
    return 0


def _h_info(res: Resolution) -> int:
    try:
        recipe = _load_recipe(res)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"cru: {exc}", file=sys.stderr)
        return 1
    archive = (
        recipe.output.custom_name or f"{recipe.project_name}-{recipe.device.codename}"
    ) + recipe.output.format.value
    print(f"project       : {recipe.project_name}")
    print(f"manifest      : {recipe.rom.source} ({recipe.rom.branch})")
    print(f"lunch combo   : {recipe.lunch_combo()}")
    print(f"build target  : {recipe.rom.build_target}")
    print(f"device        : {recipe.device.codename}")
    print(
        f"repositories  : {len(recipe.device.repositories)} remote, "
        f"{len(recipe.device.files)} local"
    )
    ccache = f"enabled ({recipe.options.ccache_size})" if recipe.options.use_ccache else "disabled"
    print(f"ccache        : {ccache}")
    print(f"format        : {recipe.output.format.value}")
    print(f"archive       : {archive}")
    return 0


def _h_fetch(res: Resolution) -> int:
    from cruine.core.fetcher import SourceFetcher
    from cruine.core.patcher import Patcher

    try:
        recipe = _load_recipe(res)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"cru: {exc}", file=sys.stderr)
        return 1
    workspace = _workspace(res)
    patcher = Patcher(recipe, workspace)
    patcher.run_hooks("pre_fetch")
    jobs = _int_flag(res, "jobs") or recipe.options.parallel_jobs
    SourceFetcher(recipe, workspace, jobs=jobs).fetch()
    patcher.run_hooks("post_fetch")
    return 0


def _h_patch(res: Resolution) -> int:
    from cruine.core.patcher import Patcher

    try:
        recipe = _load_recipe(res)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"cru: {exc}", file=sys.stderr)
        return 1
    Patcher(recipe, _workspace(res)).apply_patches()
    return 0


def _h_pack(res: Resolution) -> int:
    from cruine.config.validator import RecipeValidator
    from cruine.core.packager import OutputPackager

    try:
        recipe = _load_recipe(res)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"cru: {exc}", file=sys.stderr)
        return 1
    destination = Path(res.values[0]) if res.values else Path(res.flag("output") or ".")
    source_dir: Path | None = None
    if res.flag("source"):
        source_dir = Path(res.flag("source"))
    if res.flag("format"):
        recipe.output.format = RecipeValidator.normalize_format(str(res.flag("format")))
    OutputPackager(recipe, _workspace(res), destination, source_dir=source_dir).package()
    return 0


def _h_extract(res: Resolution) -> int:
    from cruine.core.extractor import RomExtractor
    from cruine.utils.urls import strip_archive_suffix

    if not res.values:
        print("cru: extract requires an archive path", file=sys.stderr)
        return 2
    archive = res.values[0]
    default = strip_archive_suffix(Path(archive).name)
    output = Path(res.flag("output") or res.flag("path") or default)
    count = RomExtractor().extract(archive, output)
    print(f"Extracted {count} file(s) from {Path(archive).name} -> {output}")
    return 0


def _h_repack(res: Resolution) -> int:
    from cruine.cli import PipelineOptions, run_repack

    if not res.values:
        print("cru: repack requires an archive path", file=sys.stderr)
        return 2
    archive = res.values[0]
    destination = Path(res.values[1]) if len(res.values) > 1 else Path(res.flag("output") or ".")
    work_dir: Path | None = None
    if res.flag("work-dir"):
        work_dir = Path(res.flag("work-dir"))
    elif res.flag("path"):
        work_dir = Path(res.flag("path"))
    opts = PipelineOptions(
        destination=destination,
        recipe=Path(res.flag("recipe")) if res.flag("recipe") else None,
        work_dir=work_dir,
        verbose=bool(res.flag("verbose")),
        no_color=bool(res.flag("no-color")),
        dry_run=bool(res.flag("dry-run")),
        skip_fetch=bool(res.flag("skip-fetch") or res.flag("no-fetch")),
        skip_package=bool(res.flag("skip-package")),
    )
    return run_repack(
        opts,
        archive=archive,
        output_format=str(res.flag("format")) if res.flag("format") else None,
    )


def _h_build(res: Resolution) -> int:
    from cruine.cli import PipelineOptions, run_pipeline

    destination = Path(res.values[0]) if res.values else Path(res.flag("output") or ".")
    work_dir: Path | None = None
    if res.flag("work-dir"):
        work_dir = Path(res.flag("work-dir"))
    elif res.flag("path"):
        work_dir = Path(res.flag("path"))
    opts = PipelineOptions(
        destination=destination,
        recipe=Path(res.flag("recipe")) if res.flag("recipe") else None,
        work_dir=work_dir,
        jobs=_int_flag(res, "jobs"),
        verbose=bool(res.flag("verbose")),
        no_color=bool(res.flag("no-color")),
        dry_run=bool(res.flag("dry-run")),
        skip_fetch=bool(res.flag("skip-fetch") or res.flag("no-fetch")),
        skip_package=bool(res.flag("skip-package")),
        clean=bool(res.flag("clean")),
        mem_limit=_int_flag(res, "mem-limit"),
    )
    return run_pipeline(opts)


def _h_env(res: Resolution) -> int:
    from cruine.core.environment import EnvironmentManager

    report = EnvironmentManager().inspect_host()
    print(f"python  : {report.python_version}")
    print(f"cores   : {report.cpu_cores}")
    print(f"memory  : {report.total_memory_gb} GB")
    print(f"libc    : {report.libc} ({report.arch}, {report.target_triple})")
    print(f"cc/cxx  : {report.cc} / {report.cxx}")
    print(f"tools   : {', '.join(sorted(report.tools.present)) or '(none)'}")
    missing = report.missing_required + report.missing_build_tools + report.missing_optional
    print(f"missing : {', '.join(missing) or '(none)'}")
    if report.java.java:
        jdk = "yes" if report.java.is_jdk else "no"
        print(f"java    : {report.java.version or 'unknown version'} (JDK: {jdk})")
    return 0


def _h_log(res: Resolution) -> int:
    scan_dir = Path(res.flag("dir")) if res.flag("dir") else Path.cwd()
    logs = sorted(scan_dir.glob("*-build.log"), key=lambda path: path.stat().st_mtime)
    if not logs:
        print(f"no build logs found in {scan_dir}")
        return 1
    target = logs[-1]
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
    print(f"--- {target} ---")
    for line in lines:
        print(line)
    return 0


def _h_ccache(res: Resolution) -> int:
    import shutil
    import subprocess

    ccache = shutil.which("ccache")
    if not ccache:
        print("ccache not installed")
        return 1
    proc = subprocess.run([ccache, "-s"], capture_output=True, text=True, check=False)
    print(proc.stdout or proc.stderr or "")
    return proc.returncode


def _h_jobs(res: Resolution) -> int:
    from cruine.core.environment import EnvironmentManager

    print(f"recommended jobs: {EnvironmentManager().inspect_host().recommended_jobs}")
    return 0


def _h_path(res: Resolution) -> int:
    if res.values:
        node = _find_by_path(res.values)
        if node is None:
            print(f"unknown command path: {' '.join(res.values)}", file=sys.stderr)
            return 2
        print(" ".join(res.values), "->", " ".join(_full_path(node)))
        return 0
    print(" ".join(res.path))
    return 0


def _h_tree(res: Resolution) -> int:
    depth = int(res.values[0]) if res.values and res.values[0].isdigit() else 3
    depth = max(1, min(depth, 25))
    _print_tree(TREE, 0, depth)
    return 0


def _h_help(res: Resolution) -> int:
    if not res.values:
        print("Cruine command tree (top level):")
        _print_tree(TREE, 0, 2)
        print("\nTip: cru help <path>  |  cru tree <depth>  |  cru <cmd> --help")
        return 0
    node = _find_by_path(res.values)
    if node is None:
        print(f"unknown command path: {' '.join(res.values)}", file=sys.stderr)
        return 2
    _print_node(node, res.values)
    return 0


def _h_config(res: Resolution) -> int:
    from cruine.config.settings import (
        config_path,
        format_config,
        load_settings,
        write_template,
    )
    from cruine.utils.logger import configure_logger

    action = res.values[0] if res.values else "show"
    if action in ("init", "write", "template", "new"):
        dir_flag = res.flag("dir")
        target = Path(str(dir_flag)) / "config.toml" if dir_flag else config_path()
        try:
            written = write_template(target)
        except FileExistsError as exc:
            print(f"cru: {exc}", file=sys.stderr)
            return 1
        print(f"Example config written to: {written}")
        return 0
    if action in ("reload", "load", "refresh", "reapply"):
        settings = load_settings()
        configure_logger(settings=settings)
        print(f"config reloaded from: {config_path()}")
        return 0
    if action in ("path", "location", "file"):
        print(config_path())
        return 0
    if action in ("format", "effective", "show", "get"):
        settings = load_settings()
        print(format_config(settings))
        return 0
    print(f"cru: unknown config action: {action}", file=sys.stderr)
    print("usage: cru config [show|reload|init|path] [--dir <path>]", file=sys.stderr)
    return 2


def _h_shell(res: Resolution) -> int:
    from cruine.shell import Repl

    start = res.values[0] if res.values else str(res.flag("path") or "")
    return Repl(start_path=start.strip("/") or None, no_color=bool(res.flag("no-color"))).run()


HANDLERS: dict[str, Callable[[Resolution], int]] = {
    "echo": _h_echo,
    "describe": _h_describe,
    "version": _h_version,
    "formats": _h_formats,
    "init": _h_init,
    "doctor": _h_doctor,
    "info": _h_info,
    "fetch": _h_fetch,
    "patch": _h_patch,
    "pack": _h_pack,
    "extract": _h_extract,
    "repack": _h_repack,
    "build": _h_build,
    "env": _h_env,
    "log": _h_log,
    "ccache": _h_ccache,
    "jobs": _h_jobs,
    "path": _h_path,
    "tree": _h_tree,
    "help": _h_help,
    "config": _h_config,
    "shell": _h_shell,
}
