"""Main Click/Argparse CLI implementation."""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from cruine import __version__
from cruine.commands import dispatch, is_top_command
from cruine.config.loader import RecipeLoader
from cruine.config.validator import RecipeValidator
from cruine.core.environment import EnvironmentManager
from cruine.core.executor import BuildExecutor
from cruine.core.extractor import RomExtractor
from cruine.core.fetcher import SourceFetcher
from cruine.core.packager import OutputPackager
from cruine.core.patcher import Patcher
from cruine.models.output import OutputFormat
from cruine.models.recipe import RecipeSchema
from cruine.utils.logger import configure_logger, log

EPILOG = """\
examples:
  cru /home/user/build_outputs
  cru /home/user/build_outputs --recipe ./recipes/pixel.json
  cru /home/user/build_outputs --dry-run
  cru /home/user/build_outputs --skip-fetch --clean -j 16
  cru --generate-template ./rc.json

supported output formats:
  .zip  .tar.gz  .tar.bz2  .tar.xz  .tgz  .7z  .img  .iso  .tar
"""


@dataclass
class PipelineOptions:
    destination: Path
    recipe: Path | None = None
    work_dir: Path | None = None
    jobs: int | None = None
    verbose: bool = False
    no_color: bool = False
    dry_run: bool = False
    skip_fetch: bool = False
    skip_package: bool = False
    clean: bool = False
    mem_limit: int | None = None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cru",
        description="Cruine - Android Custom ROM build automation engine.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )
    parser.add_argument(
        "destination",
        nargs="?",
        help="destination directory for the final archived ROM",
    )
    parser.add_argument(
        "-r",
        "--recipe",
        help="path to a non-standard recipe file (default: ./rc.json)",
    )
    parser.add_argument(
        "-w",
        "--work-dir",
        help="build workspace directory (default: <cwd>/<project_name>)",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        help="number of parallel build jobs (overrides recipe options)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="enable verbose (debug) logging",
    )
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the recipe and print the execution plan without running anything",
    )
    parser.add_argument(
        "--skip-fetch",
        "--no-fetch",
        dest="skip_fetch",
        action="store_true",
        help="skip source fetching and use the existing tree",
    )
    parser.add_argument(
        "--skip-package",
        action="store_true",
        help="build but do not package the outputs",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="force a clean build (mka clean before building)",
    )
    parser.add_argument(
        "--mem-limit",
        type=int,
        metavar="MB",
        help="enforce a virtual-memory ulimit during the build",
    )
    parser.add_argument(
        "-g",
        "--generate-template",
        metavar="PATH",
        help="write an example rc.json recipe and exit",
    )
    parser.add_argument(
        "--list-formats",
        action="store_true",
        help="list supported output archive formats and exit",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"Cruine {__version__}",
    )
    return parser


def _dry_run(
    recipe: RecipeSchema,
    opts: PipelineOptions,
    workspace: Path,
    destination: Path,
) -> int:
    log.info("DRY RUN - validating recipe and printing the plan (nothing will be executed)")
    archive = (
        recipe.output.custom_name or f"{recipe.project_name}-{recipe.device.codename}"
    ) + recipe.output.format.value
    log.success(f"Project      : {recipe.project_name}")
    log.info(f"Manifest     : {recipe.rom.source} ({recipe.rom.branch})")
    log.info(f"Lunch combo  : {recipe.lunch_combo()}")
    log.info(f"Build target : {recipe.rom.build_target}")
    log.info(f"Device       : {recipe.device.codename}")
    log.info(
        f"Sources      : {len(recipe.device.repositories)} remote tree(s), "
        f"{len(recipe.device.files)} local file set(s)"
    )
    ccache_state = (
        f"enabled ({recipe.options.ccache_size})" if recipe.options.use_ccache else "disabled"
    )
    jobs = opts.jobs or recipe.options.parallel_jobs
    if jobs:
        log.info(f"Jobs         : {jobs}")
    log.info(f"CCACHE       : {ccache_state}")
    log.info(f"Clean build  : {'yes' if opts.clean or recipe.options.clean_build else 'no'}")
    log.info(f"Format       : {recipe.output.format.value}")
    log.info(f"Archive      : {archive}")
    log.info(f"Workspace    : {workspace}")
    log.info(f"Destination  : {destination}")
    if recipe.input.archive:
        log.info(
            f"Input        : {recipe.input.archive}"
            f" ({recipe.input.format or 'auto-detected'}) -> REPACK MODE"
        )
    return 0


def _workspace_for(recipe: RecipeSchema, opts: PipelineOptions) -> Path:
    return Path(opts.work_dir) if opts.work_dir else Path.cwd() / recipe.project_name


def _run_repack(
    recipe: RecipeSchema,
    opts: PipelineOptions,
    workspace: Path,
    destination: Path,
) -> int:
    if not recipe.input.archive:
        log.critical("Repack requested but recipe defines no input.archive")
        return 1
    if opts.dry_run:
        return _dry_run(recipe, opts, workspace, destination)

    destination.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    extractor = RomExtractor(workspace=workspace)
    out_dir = extractor.product_dir(recipe.device.codename)

    patcher = Patcher(recipe, workspace)
    patcher.run_hooks("pre_fetch")

    if opts.skip_fetch:
        log.warning("Skipping extraction (--skip-fetch); assuming the tree is already extracted")
        if not out_dir.is_dir():
            log.critical(f"Extracted tree not found: {out_dir}")
            return 1
    else:
        if out_dir.exists():
            log.info(f"Removing previous extraction: {out_dir}")
            shutil.rmtree(out_dir)
        extractor.extract(recipe.input.archive, out_dir)

    patcher.run_hooks("post_fetch")
    patcher.apply_patches()
    patcher.run_hooks("pre_build")
    patcher.run_hooks("post_build")

    if not opts.skip_package:
        packager = OutputPackager(recipe, workspace, destination)
        artifact = packager.package()
        log.success(f"Repacked artifact: {artifact}")
    else:
        log.warning("Skipping packaging (--skip-package)")

    return 0


def run_repack(
    opts: PipelineOptions,
    archive: str | None = None,
    input_format: str | None = None,
    output_format: str | None = None,
) -> int:
    """Repack an existing ROM archive through a recipe (used by `cru repack`)."""
    configure_logger(verbose=opts.verbose or None, no_color=opts.no_color or None)

    start = time.monotonic()
    try:
        loader = RecipeLoader()
        recipe = (
            loader.load_from_path(Path(opts.recipe))
            if opts.recipe
            else loader.auto_discover_and_load()
        )
        if archive:
            recipe.input.archive = archive
        if input_format:
            recipe.input.format = input_format
        if output_format:
            recipe.output.format = RecipeValidator.normalize_format(str(output_format))
        workspace = _workspace_for(recipe, opts)
        result = _run_repack(recipe, opts, workspace, Path(opts.destination))
    except KeyboardInterrupt:
        log.warning("Interrupted by user")
        return 130
    except Exception as exc:
        if opts.verbose:
            raise
        log.critical(str(exc))
        return 1
    else:
        if result == 0:
            elapsed = int(time.monotonic() - start)
            log.success(f"Repack finished successfully in {elapsed}s")
        return result


def run_pipeline(opts: PipelineOptions) -> int:
    configure_logger(verbose=opts.verbose or None, no_color=opts.no_color or None)

    destination = Path(opts.destination)
    if destination.exists() and not destination.is_dir():
        log.critical(f"Destination exists and is not a directory: {destination}")
        return 1

    start = time.monotonic()
    try:
        loader = RecipeLoader()
        recipe = (
            loader.load_from_path(Path(opts.recipe))
            if opts.recipe
            else loader.auto_discover_and_load()
        )

        workspace = _workspace_for(recipe, opts)

        if recipe.input.archive:
            log.info("Recipe defines input.archive -> entering repack mode")
            return _run_repack(recipe, opts, workspace, destination)

        if opts.dry_run:
            return _dry_run(recipe, opts, workspace, destination)

        destination.mkdir(parents=True, exist_ok=True)
        workspace.mkdir(parents=True, exist_ok=True)

        env_manager = EnvironmentManager()
        report = env_manager.validate()
        if not report.ready:
            log.critical("Environment validation failed; install the missing tools and try again.")
            return 1

        ok, free_gb = env_manager.check_disk_space(Path.cwd(), 10.0)
        if not ok:
            log.warning(
                f"Low free disk space on {Path.cwd().resolve()}: {free_gb:.1f} GB "
                "(AOSP builds can require 200+ GB)"
            )

        env_manager.setup_ccache(recipe)

        jobs = opts.jobs or recipe.options.parallel_jobs or report.recommended_jobs
        build_env = env_manager.build_environment(recipe, jobs)

        patcher = Patcher(recipe, workspace)
        patcher.run_hooks("pre_fetch")

        if not opts.skip_fetch:
            fetcher = SourceFetcher(recipe, workspace, jobs=jobs)
            fetcher.fetch()
            patcher.run_hooks("post_fetch")
            patcher.apply_patches()
        else:
            log.warning("Skipping source fetch (--skip-fetch); assuming tree is present")

        patcher.run_hooks("pre_build")

        log_file = destination / f"{recipe.project_name}-build.log"
        executor = BuildExecutor(recipe, workspace, log_file=log_file, mem_limit_mb=opts.mem_limit)
        executor.build(build_env, clean=opts.clean or recipe.options.clean_build)

        patcher.run_hooks("post_build")

        if not opts.skip_package:
            packager = OutputPackager(recipe, workspace, destination)
            artifact = packager.package()
            log.success(f"Final artifact: {artifact}")
        else:
            log.warning("Skipping packaging (--skip-package)")

    except KeyboardInterrupt:
        log.warning("Interrupted by user")
        return 130
    except Exception as exc:
        if opts.verbose:
            raise
        log.critical(str(exc))
        return 1
    else:
        elapsed = int(time.monotonic() - start)
        log.success(f"Pipeline finished successfully in {elapsed}s")
        return 0


def _main(argv: list[str]) -> int:
    raw = argv if argv is not None else sys.argv[1:]

    if raw and is_top_command(raw[0]):
        return dispatch(raw)

    parser = _build_parser()
    args = parser.parse_args(raw)

    if args.generate_template:
        try:
            path = RecipeLoader.write_template(Path(args.generate_template))
        except Exception as exc:
            parser.error(str(exc))
            return 2
        print(f"Example rc.json written to: {path}")
        return 0

    if args.list_formats:
        for fmt in OutputFormat:
            print(fmt.value)
        return 0

    if args.destination is None:
        parser.error("the following arguments are required: destination")
        return 2

    return run_pipeline(
        PipelineOptions(
            destination=Path(args.destination),
            recipe=Path(args.recipe) if args.recipe else None,
            work_dir=Path(args.work_dir) if args.work_dir else None,
            jobs=args.jobs,
            verbose=args.verbose,
            no_color=args.no_color,
            dry_run=args.dry_run,
            skip_fetch=args.skip_fetch,
            skip_package=args.skip_package,
            clean=args.clean,
            mem_limit=args.mem_limit,
        )
    )


def main(argv: list[str] | None = None) -> int:
    raw = argv if argv is not None else sys.argv[1:]
    try:
        return _main(raw)
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            return code
        return 2 if code else 0


if __name__ == "__main__":
    raise SystemExit(main())
