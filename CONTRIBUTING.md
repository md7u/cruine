# Contributing to Cruine

Thanks for helping with Cruine, the Android Custom ROM build automation
engine. This guide covers the development workflow.

## Project layout

```
src/              The `cruine` Python package (package_dir: cruine = ".")
  commands/       Command tree: model, flags, builders, resolver, handlers, dispatch
  config/         rc.json discovery and validation
  core/           environment, fetcher, patcher, executor, packager
  models/         pydantic schemas (one model per file)
  tests/          pytest suite (including the full-pipeline integration test)
  shell.py        Interactive REPL over the command tree
docs/             Man pages (cru(1), crush(1), rc.json(5))
examples/         Example recipes, one subfolder per scenario
scripts/          Standalone launcher bundled by PyInstaller
```

## Development setup

```sh
python3 -m venv .venv
python3 -m pip --python .venv/bin/python install "./src[dev]"
.venv/bin/python -m pytest src/tests
```

## Quality gates

All checks must pass before a pull request is merged:

```sh
make test      # .venv/bin/python -m pytest src/tests
make lint      # ruff check + ruff format --check on src/
```

The suite includes `tests/test_integration.py`, which drives the real
`cru <destination>` pipeline end-to-end against a synthetic tree (git
clone, bash build, zip packaging) and requires `git`/`bash`/`tar` on PATH.

## Building the standalone binary

Cruine is bundled into a single self-contained executable with PyInstaller:

```sh
make deps      # create .venv, install dependencies + pyinstaller
make build     # emit target/cru
make install   # install to $(PREFIX)/bin/cru and man pages
```

The generated binary does not require a system Python installation.

## Code style

* Python 3.10+ with explicit type annotations on every signature.
* One class per file; keep modules small and focused.
* Use the existing `cruine.utils.logger` for all terminal output.
* Do not add comments that restate the code; document intent instead.

## Submitting changes

1. Format and lint your changes: `make lint`.
2. Add tests for new behaviour under `src/tests/`.
3. If a recipe field or command changes, update the matching man page in
   `docs/` and any affected examples in `examples/`.
4. Open a pull request against the default branch.

## Reporting bugs

Use the issue tracker and include the `cru` version, the `rc.json`
(sanitised), and the full command invocation plus error output.
