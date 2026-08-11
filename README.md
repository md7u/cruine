# Cruine

![Version](https://img.shields.io/badge/Version-0.1.0-21262d?style=flat&labelColor=161b22)
![Platform](https://img.shields.io/badge/Platform-Android-21262d?style=flat&labelColor=161b22)
![Build](https://img.shields.io/badge/Build-Passing-21262d?style=flat&labelColor=161b22)
![License](https://img.shields.io/badge/License-MIT-21262d?style=flat&labelColor=161b22)

An Android Custom ROM builder, automates the complete Android Custom ROM build pipeline by reading a recipe, syncs the ROM manifest and device source trees validates the host environment, configures ccache, resolves the lunch combo, runs the build applies patches and lifecycle hooks, and packages the output into a configurable archive at a given destination.

```sh
cru /tmp/rom-out
```

---

## Usage

- **Legacy** — `cru <destination>` runs every stage in one command.
- **Command** — `cru <command>` drives individual stages and inspection tools, exposed through a large command tree with shell (`cru crush`).

Both methods share the same recipe format, the same core stages, and the same
options.

---

## Starting

Building a custom ROM manually consists of the following operations, in
order:

1. Clone and check out the ROM manifest at the requested branch with the
   native sync engine (equivalent of `repo init`).
2. Synchronize every active project in the manifest with plain `git`
   (equivalent of `repo sync`; tens of gigabytes, often repeated when the
   network drops).
3. Clone the device, kernel, and vendor trees into their required locations
   under the workspace (e.g. `device/xiaomi/alioth`,
   `kernel/xiaomi/alioth`, `vendor/xiaomi/alioth`).
4. Install and configure ccache with a size limit.
5. Load the build environment (`source build/envsetup.sh`), select the
   combination with `lunch <prefix>_<device>-<variant>`, and invoke
   `mka <target> -j<jobs>`.
6. Wait for the build to finish, monitoring disk and memory.
7. Package the firmware from `out/target/product/<device>/` into a
   flashable archive.

Each step is an opportunity for a specific class of mistake, each of which
can invalidate hours of compute:

- Wrong or stale manifest branch.
- Missing or misplaced device/kernel/vendor tree.
- Incorrect lunch prefix, codename, or variant.
- Build run without ccache (or with a misconfigured cache).
- Archive produced from a stale `out/` directory.
- Disk filling up mid-build.
- Wrong output format or compression for the target hardware.

Cruine makes each of these steps explicit and validated. `rc.json` fixes the
parameters; the pipeline checks the environment before running; `--dry-run`
prints the entire plan before anything executes.

---

## Components

| Concept | Definition |
|---|---|
| Recipe | The `rc.json` file describing one build: ROM, device, options, output, patches, hooks. Discovered in the current working directory, or passed explicitly with `-r/--recipe`. |
| Workspace | The directory where sources are synced and the build runs. Defaults to `<cwd>/<project_name>`. |
| Destination | The directory that receives the build log and the final packaged artifact. |
| Manifest | The upstream ROM manifest (git URL and branch) that defines the contents of the source tree. |
| Lunch combo | The AOSP build selector, composed as `<lunch_prefix>_<codename>-<build_variant>` (e.g. `lineage_alioth-userdebug`). |
| Build target | The make target passed to `mka`; typically `bacon`. |
| Sources | Extra trees required beyond the manifest: `device`, `kernel`, `vendor`, or `other`, acquired as git clones, `file://` local repos, or copied from local directories. |
| Input | An existing ROM archive (`input.archive`) that switches the pipeline into repack mode instead of building from source. |
| Repack | Extract a ROM archive, apply patches and hooks to its contents, and re-archive it. Driven by `input` in the recipe, or manually via `cru extract` / `cru pack --source`. |
| ccache | Compiler cache that accelerates repeated builds; enabled by default. |
| Patch | A `git apply`-able diff applied to the workspace after fetching. |
| Hook | A shell command run at a named pipeline phase. |
| Artifact | The packaged build output (`.zip`, `.tar.gz`, `.7z`, `.img`, `.iso`, etc.). |

---

## Requirements

A full legacy invocation runs the following stages in order. Each stage can
be skipped (via flags) or executed alone (via the command tree).

### 1. Recipe

The current directory is scanned for `rc.json`, unless `-r/--recipe FILE`
names a specific file. The recipe is parsed and validated against a strict
schema. A malformed or incomplete recipe aborts the run before any I/O
occurs.

### 2. Destination

The destination directory is created if it does not exist. If the
destination exists and is not a directory, the run aborts. In `--dry-run`
mode nothing is created.

### 3. Environment

The host is checked for required tools: `git`, `bash`, `tar`, `python3`,
`make`, `java`, and `javac`. A missing JDK (`java`/`javac`) aborts the run —
AOSP cannot build without one. Missing required tools abort the run and are
listed in the error. `repo` is **not** required — Cruine syncs manifests
natively with plain `git`. Optional fallback tools (`ccache`, `7z`,
`mkisofs`, `genisoimage`, `xorriso`, `unzip`) degrade specific features
instead of aborting, and common AOSP/Kernel host tools (`curl`, `rsync`,
`lzip`, `xz`, `zstd`, `lz4`, `bc`, `bison`, `flex`, `openssl`, `git-lfs`,
`schedtool`, `m4`, `perl`, `clang`, `clang++`, `gcc`, `g++`, `ninja`,
`cmake`) are reported as warnings when missing. `cru doctor` performs this
check standalone and also reports the detected libc/toolchain profile
(Cudane → musl + clang/clang++, glibc → gcc/g++) and the detected JDK
version against the usual AOSP targets (JDK 8 for Android ≤ 10, JDK 11 for
Android 11–12, JDK 17 for Android 13+).

### 4. Disk space

Free disk space in the working directory is checked. Below 10 GB the run
continues with a warning (AOSP builds commonly require 200+ GB).

### 5. CCache

When the recipe enables ccache (the default), the cache directory is
created, the size limit is configured (default `50G`), and the standard
ccache environment variables are exported. The default cache directory is
`~/.cache/ccache` (override with `CCACHE_DIR`).

### 6. Jobs

The parallel job count is resolved in this order: CLI `--jobs` flag,
`options.parallel_jobs` in the recipe, then a host-derived recommendation of
`min(CPU cores, 16)`, minimum 1. The result is exported as `CRU_JOBS`.

### 7. Source

Unless `--skip-fetch`/`--no-fetch` is given:

- The ROM manifest is cloned and checked out at the branch named in the
  recipe using the **native sync engine** (no `repo` binary), then every
  active project in the manifest is cloned with plain `git`. Any URL form
  (`https`, `ssh`, `git`, `file://`, scp-style `git@host:path`, plain local
  path) and any revision (branch, tag, or SHA-1) is supported. State is kept
  in `<workspace>/.cruine/` so unchanged projects skip the network on repeat
  runs; extra projects can be pinned in `.cruine/local_manifests/*.xml`.
- Each entry in `device.repositories` is cloned into its declared
  `target_path`; `file://` URLs clone from local repositories.
- Each entry in `device.files` is copied recursively from its local `url`.
- Failed syncs/clones are retried automatically.

### 7a. Repack (input archive)

When the recipe defines `input.archive`, the fetch/build stages are replaced
by extraction: the archive is unpacked into
`out/target/product/<codename>`, then patches and hooks run, then the tree
is packaged.

### 8. Post-fetch hooks and patches

`post_fetch` hooks run, then every patch is applied with `git apply` at the
configured `strip` level (default 1) inside the configured directory
(default `.`).

### 9. Pre-build hooks

`pre_build` hooks run in the workspace before the build starts.

### 10. Build

Inside the workspace, in order:

1. `source build/envsetup.sh`
2. If a clean build was requested (`--clean` or `options.clean_build`):
   `mka clean`, falling back to `make clean`.
3. `lunch <lunch_combo>`
4. `mka <build_target> -j<jobs>`, with any `options.extra_make_args`
   appended to the command.

The sequence runs as a single shell script. If `--mem-limit MB` is set, a
virtual-memory ulimit (`ulimit -v`) wraps the build. Output is streamed to
`<destination>/<project_name>-build.log`.

### 11. Post-build hooks

`post_build` hooks run after the build and before packaging.

### 12. Packaging

Unless `--skip-package`, the device output tree
(`out/target/product/<codename>`) is packaged into the configured format and
compression level, excluding `exclude_dirs` (default `obj` and `symbols`).
The archive is written to the destination and its path is printed.

### 13. Report

Elapsed time and the final artifact path are printed. Exit code `0`
indicates a completed pipeline.

---

## Installation

Cruine is a pure-Python project (Python 3.10+). Recommended setup:

```sh
python3 -m venv .venv
.venv/bin/pip install "./src[dev]"
.venv/bin/python -m pytest src/tests   # optional: run the test suite
```

Or build as binary:

```sh
make build      # produces target/cru via PyInstaller
make install    # installs cru + man pages under $(PREFIX)
```

The PyInstaller binary is self-contained and requires no system Python.

The install prefix is auto-detected by `scripts/detect.sh`: **`/system`** on
Cudane (musl-libc/LLVM) and **`/usr`** on glibc GNU/Linux distributions.
Override with `make install PREFIX=/custom` (Make), `DESTDIR=/mnt ninja
install` (Ninja), or `meson setup build -Dprefix=/custom` (Meson).

### Dependencies

- Runtime: `pydantic`, `py7zr`, `pycdlib`.
- Dev/test: `pytest`, `ruff`.
- Build: `make`, `ninja`, or `meson`; `python3` + `pip`; `pyinstaller`.
- Host tools checked at run time: `git`, `bash`, `tar` (required; `repo` is
  no longer needed — sync is native); `ccache`, `7z`, `mkisofs`,
  `genisoimage`, `xorriso`, `unzip` (optional).
- Toolchain (auto-detected by libc): on **Cudane** (musl-libc) — `clang`,
  `clang++`, and the musl toolchain; on **glibc** distributions — `gcc`,
  `g++`. Both compiler pairs are probed; the active profile picks the pair.
  Targets: `x86_64-unknown-linux-musl` / `aarch64-unknown-linux-musl` on
  Cudane, `x86_64-unknown-linux-gnu` / `aarch64-unknown-linux-gnu` elsewhere.

---

## Build system

Cruine is built with any of four interchangeable backends — Make, Ninja,
Meson, or CMake. They all delegate the packaging step to the same script, so
the artifact is identical regardless of the frontend.

| File | Role |
|---|---|
| `scripts/detect.sh` | Central host-profile detector: prints `distro`, `libc` (musl/glibc), `arch` (amd64/arm64), `prefix` (`/system` on Cudane, `/usr` otherwise), `cc`/`cxx`, and the target `triple`. Overrides: `CRUINE_LIBC`, `CRUINE_PREFIX`, `CC`, `CXX`. |
| `env.mk` | Make variables for `Makefile`: `PREFIX`, `CC`, `CXX`, `LIBC`, `ARCH`, `TARGET_TRIPLE` — all sourced from `scripts/detect.sh` unless overridden on the command line. |
| `Makefile` | Primary build. `make build` (binary), `make install`, `make test`, `make lint`, `make uninstall`, `make clean`. |
| `build.ninja` | Ninja build. `ninja` then `DESTDIR=/mnt ninja install`; install prefix detected at run time. |
| `meson.build` | Meson build. `meson setup build && meson compile -C build && meson install -C build`; honors `-Dprefix=...`, defaults to the detected prefix. |
| `scripts/cross.sh` | Generates the Meson cross-file `cross.txt` for the detected profile (compiler, full target triple, `/system` vs `/usr` include/lib dirs). Run automatically by `meson.build`; standalone usage: `./scripts/cross.sh [output]`. |
| `toolchain.cmake` | CMake toolchain for the detected profile (compiler, `CMAKE_FIND_ROOT_PATH` = detected prefix). |
| `scripts/pkgconfig.sh` | `pkg-config` wrapper pointing `PKG_CONFIG_LIBDIR` at the detected prefix (`/system/lib/pkgconfig` on Cudane, `/usr/lib/pkgconfig` otherwise). |
| `scripts/package.sh` | Builds the PyInstaller binary into a scratch venv (non-editable install) and runs `packaging/cru.spec`. Used by Make, Ninja, and Meson. |
| `packaging/cru.spec` | PyInstaller spec; collects third-party data/dylibs (`pydantic`, `py7zr`, `pycdlib`). |

### Host profiles

The build files and `cru doctor` share one model of the host:

- **Cudane** — musl-libc, LLVM/clang. Installs under `/system`; target triples
  `x86_64-unknown-linux-musl` and `aarch64-unknown-linux-musl` (both amd64 and
  arm64 are supported). Detected when `/etc/os-release` reports `ID=cudane` or
  a musl loader (`/lib/ld-musl-*.so.1`) is present; force with
  `CRUINE_LIBC=musl`.
- **glibc GNU/Linux** — glibc, GCC. Installs under `/usr`; target triples
  `x86_64-unknown-linux-gnu` / `aarch64-unknown-linux-gnu`.

---

## Quick start

```sh
cru init ./rc.json              # write a starter recipe
cru info                        # print the plan for the active recipe
cru /tmp/rom-out                # full pipeline, all defaults
cru /tmp/rom-out --skip-fetch -j 16   # rebuild, reuse the tree
cru tree 3                      # render the command tree
cru crush                       # shell
cru doctor                      # validate the host
```

---

## Recipes

`rc.json` is a single JSON document describing a build. It is found in the
current working directory or named explicitly with `-r/--recipe`. A template
is generated with `cru init <target>` or `cru --generate-template PATH`.

### `project_name` (required)

String. Short build name (e.g. `LineageOS-PocoF3`). Used for the default
workspace directory, the build log filename, and the default archive
basename.

### `rom` (required)

| Key | Required | Meaning | Example |
|---|---|---|---|
| `source` | yes | Git URL of the ROM manifest (or `file://` path / local git repo for offline builds) | `https://github.com/LineageOS/android.git` |
| `branch` | yes | Manifest branch | `lineage-21.0` |
| `lunch_prefix` | yes | Prefix used by `lunch` | `lineage` |
| `build_target` | yes | Make target passed to `mka` | `bacon` |
| `manifest` | no | Manifest file inside the manifest repo (defaults to `default.xml`/`manifest.xml`) | `snapshot.xml` |
| `groups` | no | Manifest groups to sync, comma-separated; defaults to the `default` group. Prefix with `-` to exclude (e.g. `default,-pdk`) | `default` |
| `depth` | no | Shallow-clone depth for the manifest repo and projects | `1` |

The lunch combo is `<lunch_prefix>_<codename>-<build_variant>`, e.g.
`lineage_alioth-userdebug`.

A `file://` source makes the build fully local: the manifest is initialized
from a local git repository instead of being fetched over the network, and
`device.repositories` URLs in the manifest may also point at local repos.
Plain filesystem paths are accepted the same way (`file:///srv/rom/manifest`
and `/srv/rom/manifest` are equivalent). Relative `fetch` values in the
manifest resolve against the manifest URL exactly like the AOSP tools, so
self-hosted mirrors work without rewriting the manifest.

### `device` (required)

| Key | Required | Meaning |
|---|---|---|
| `codename` | yes | Device codename; locates output under `out/target/product/<codename>` |
| `repositories` | no | Remote source trees to clone |
| `files` | no | Local source sets to copy |

At least one of `repositories` or `files` is required. Entries in both use
the same shape:

| Key | Meaning | Example |
|---|---|---|
| `type` | `device`, `kernel`, `vendor`, or `other` | `kernel` |
| `url` | Git URL, `file://` path, or local path | `https://github.com/LineageOS/android_kernel_xiaomi_alioth.git` |
| `target_path` | Placement inside the workspace | `kernel/xiaomi/alioth` |

`repositories` URLs may be git URLs or local repositories
(`file:///srv/git/kernel.git`); `files` URLs are always local paths and are
copied recursively.

### `input` (optional)

When present, the pipeline switches to **repack mode**: instead of fetching
sources and building, the named ROM archive is extracted into the product
tree, the recipe's patches and hooks are applied, and the result is
re-archived.

| Key | Default | Meaning |
|---|---|---|
| `archive` | `null` | Path (or `file://` path) of an existing ROM archive to extract |
| `format` | auto-detected | Archive format override: `.zip`, `.tar`, `.tar.gz`, `.tar.bz2`, `.tar.xz`, `.tgz`, or `.7z` |

Repack mode runs, in order: `pre_fetch` hooks, extraction, `post_fetch` hooks,
patches, `pre_build` hooks, `post_build` hooks, then packaging. The extracted tree
lives in `out/target/product/<codename>` under the workspace, so hooks can
reference it with a relative path. `--skip-fetch` in repack mode skips
extraction and reuses the existing tree.

### `options` (optional)

| Key | Default | Meaning |
|---|---|---|
| `use_ccache` | `true` | Enable ccache |
| `ccache_size` | `50G` | ccache size limit (`50G`, `4G`, `800M`, ...) |
| `clean_build` | `false` | Force `mka clean` before building |
| `build_variant` | `userdebug` | One of `eng`, `user`, `userdebug` |
| `parallel_jobs` | host-recommended | Parallel job count |
| `extra_make_args` | `[]` | Extra arguments appended to the `mka` invocation |

### `output` (optional)

| Key | Default | Meaning |
|---|---|---|
| `format` | `.zip` | `.zip`, `.tar.gz`, `.tar.bz2`, `.tar.xz`, `.tgz`, `.7z`, `.img`, `.iso`, or `.tar` |
| `custom_name` | `<project_name>-<codename>` | Archive basename (extension appended automatically) |
| `compression_level` | `6` | Integer 0–9 |
| `exclude_dirs` | `["obj", "symbols"]` | Directories skipped while packaging |

### `patches` (optional)

List of patches applied after fetching:

| Key | Default | Meaning |
|---|---|---|
| `file` | — | Path to a `git apply`-able diff |
| `directory` | `.` | Workspace subdirectory in which to apply |
| `strip` | `1` | Patch level, integer 0–2 |

### `hooks` (optional)

List of shell commands run at pipeline phases:

| Key | Default | Meaning |
|---|---|---|
| `name` | — | Human-readable name |
| `command` | — | Shell command run via `sh -c` |
| `phase` | `pre_build` | `pre_fetch`, `post_fetch`, `pre_build`, or `post_build` |
| `workdir` | `.` | Working directory relative to the workspace |

---

### Example: LineageOS for Xiaomi Poco F3

```json
{
  "project_name": "LineageOS-PocoF3",
  "rom": {
    "source": "https://github.com/LineageOS/android.git",
    "branch": "lineage-21.0",
    "lunch_prefix": "lineage",
    "build_target": "bacon"
  },
  "device": {
    "codename": "alioth",
    "repositories": [
      { "type": "device",
        "url": "https://github.com/LineageOS/android_device_xiaomi_alioth.git",
        "target_path": "device/xiaomi/alioth" },
      { "type": "kernel",
        "url": "https://github.com/LineageOS/android_kernel_xiaomi_alioth.git",
        "target_path": "kernel/xiaomi/alioth" },
      { "type": "vendor",
        "url": "https://github.com/TheMuppets/manifest_xiaomi_alioth.git",
        "target_path": "vendor/xiaomi/alioth" }
    ]
  },
  "options": {
    "use_ccache": true,
    "ccache_size": "50G",
    "build_variant": "userdebug",
    "parallel_jobs": 16
  },
  "output": {
    "format": ".tar.gz",
    "custom_name": "LineageOS-21.0-alioth-UNOFFICIAL",
    "compression_level": 9
  }
}
```

Additional example recipes ship in `examples/`: `local-files` (fully local
sources, no git clones), `patches-hooks` (patches plus `pre_build` and
`post_build` hooks, `.7z` output), and `repack` (extract an existing archive,
modify it with hooks, and re-archive).

---

## CLI

```sh
cru <destination> [options]
```

| Option | Meaning |
|---|---|
| `-r, --recipe FILE` | Use a non-default recipe file (default `./rc.json`) |
| `-w, --work-dir PATH` | Build workspace directory (default `<cwd>/<project_name>`) |
| `-j, --jobs N` | Parallel build jobs (overrides the recipe) |
| `-v, --verbose` | Verbose (debug) logging |
| `--no-color` | Disable ANSI colors |
| `--dry-run` | Validate the recipe and print the execution plan; execute nothing |
| `--skip-fetch, --no-fetch` | Skip source fetching; use the existing tree |
| `--skip-package` | Build without packaging outputs |
| `--clean` | Force a clean build (`mka clean`) |
| `--mem-limit MB` | Enforce a virtual-memory ulimit during the build |
| `-g, --generate-template PATH` | Write an example `rc.json` recipe and exit |
| `--list-formats` | List supported output archive formats and exit |
| `--version` | Print the Cruine version and exit |

### Dry-run output

`cru build --dry-run` (or the legacy `--dry-run` flag) prints, in order:

- Project name
- Manifest URL and branch
- Lunch combo
- Build target
- Device codename
- Source counts (remote trees and local file sets)
- ccache state (enabled with its size, or disabled)
- Whether the build will be clean
- Output format and archive filename
- Workspace path
- Destination path
- If the recipe defines `input.archive`: the archive, its format, and a
  `REPACK MODE` marker

---

## Configuration

Cruine reads an optional user config from `~/.config/cruine/config.toml`
(overridable with the `CRUINE_CONFIG` environment variable). It controls
all output formatting: the log line format, timestamp pattern, per-status
labels and colours, and the program name used by the `{program}` variable.

```toml
[general]
program = "cru"

[log]
format = "[{ts}] [{color}{status}{reset}] {message}"
timestamp_format = "%H:%M:%S"   # 24-hour clock by default
verbose = false                  # defaults; -v/--no-color flags override
no_color = false

[log.statuses]
Build = { label = "BUILDING", color = "bright_blue" }
```

Log lines default to `[HH:MM:SS] [Status] message` with the status
capitalised and colourised. Any format string is accepted and supports
variable placeholders; unknown placeholders render empty and `""` prints
bare messages.

| Variable | Meaning |
|---|---|
| `{ts}`, `{time}` | Timestamp per `timestamp_format` (24-hour by default) |
| `{date}` | `YYYY-MM-DD` date |
| `{status}`, `{label}` | Status label (capitalised first letter) |
| `{level}` | Severity level (`INFO`, `SUCCESS`, `WARN`, ...) |
| `{message}`, `{msg}` | The log message |
| `{program}`, `{pid}`, `{hostname}` | Process identity |
| `{counter}` | Running line number |
| `{elapsed}` | Seconds since the logger started |
| `{color}`, `{reset}`, `{bold}`, `{dim}` | ANSI styling (empty when colour is off) |

Over 200 named statuses ship with the logger (e.g. `Info`, `Ok`, `Warn`,
`Error`, `Fatal`, `Build`, `Fetch`, `Sync`, `Patch`, `Pack`, `Extract`,
`Verify`, `Retry`, `Timeout`, `Missing`, ...). Any can be emitted from
code or used via the dynamic call form `log.<status>("message")`.

Manage the config from the CLI:

```sh
cru config                  # show the effective settings (path + values)
cru config reload           # re-apply settings from the config file
cru config path             # print the config file location
cru config init             # write an example config.toml (default
                            #   $HOME/.config/cruine/config.toml)
cru config init --dir ./cfg # write it into a specific directory instead
```

---

## Tree

The tree has 74 top-level entries: 52 letter groups (`a`–`z`, `A`–`Z`) and
22 functional commands. In total the tree contains roughly 12,000 nodes and
the deepest command path is 25 levels.

Commands are addressed by name, alias, or slash-separated path:

```sh
cru a                # list the 'analytics' group
cru b/bundle         # run a nested command by path
cru path build       # print the canonical path of 'build'
cru tree 3           # render the tree to depth 3
```

Each group node has a fixed set of four aliases drawn from one of several
patterns (e.g. `ba bb b0 b-all`, `qq qqq q1 q-group`, `s1 ss sx s-grp`).
Member commands have three or more aliases. Alias pools are shared per
sibling level so no two siblings collide.

### Subcommands

Each group member carries a nested subcommand subtree. Subcommand names come
from a pool of verb pairs; each pair is emitted as a parent command plus
its children, two or three levels deep depending on the position in the
group. The available verb pairs are:

| Parent | Child |
|---|---|
| `run` | `show` |
| `go` | `list` |
| `do` | `view` |
| `now` | `status` |
| `on` | `off` |
| `start` | `stop` |
| `open` | `close` |
| `add` | `drop` |
| `set` | `unset` |
| `push` | `pull` |

For example, in group `b`, the member `bake` has subcommands `push`/`pull`
and `bundle` carries a `go`/`list` subtree.

### Deep chains

Every group ends with a deep chain whose nodes have the help text
`deep level <N>`. The chains draw from six word lists:

| List | Words |
|---|---|
| Planets | `mercury venus earth mars jupiter saturn uranus neptune` |
| Solar system | `sun mercury venus earth mars jupiter saturn uranus neptune pluto` |
| Zodiac | `aries taurus gemini cancer leo virgo libra scorpio sagittarius capricorn aquarius pisces` |
| Constellations | `andromeda cassiopeia cygnus` and onward |
| Greek alphabet | letter names |
| NATO phonetic | `alfa bravo charlie` and onward |

The functional command `tier` is itself a 25-deep chain (`cru tier`,
`cru deep`, `cru chain`, `cru ladder`).

---

## Groups

| Letter | Theme | Letter | Theme |
|---|---|---|---|
| `a` | analytics | `A` | aosp |
| `b` | builder | `B` | binary |
| `c` | control | `C` | crypto |
| `d` | device | `D` | debug |
| `e` | engine | `E` | emulator |
| `f` | fetch | `F` | firmware |
| `g` | git | `G` | graphics |
| `h` | host | `H` | hardware |
| `i` | image | `I` | init |
| `j` | jobs | `J` | json |
| `k` | kernel | `K` | kernel |
| `l` | log | `L` | linker |
| `m` | make | `M` | module |
| `n` | network | `N` | native |
| `o` | output | `O` | overlay |
| `p` | package | `P` | platform |
| `q` | query | `Q` | qualcomm |
| `r` | rom | `R` | runtime |
| `s` | system | `S` | security |
| `t` | tool | `T` | treble |
| `u` | update | `U` | userspace |
| `v` | vendor | `V` | vendor |
| `w` | workspace | `W` | watchdog |
| `x` | cross | `X` | xattr |
| `y` | yaml | `Y` | yocto |
| `z` | zip | `Z` | zygote |

Representative member lists:

| Group | Members (partial) | Deep chain root |
|---|---|---|
| `b` (builder) | `bake bundle binary branch backup bootstrap bench badge beacon build blueprint bolt block broadcast browse buffer bug burn byte` | `sun` |
| `q` (query) | `query qemu quick quit quote queue quash quantify qualifier quirk quadrant quantum quarantine quarry quartile quench quest quiet quintile quota` | `alpha` |
| `s` (system) | `system sync source setup status scan search snapshot strip sign safety sample sandbox save scale scheme score script scrub secure seed select` | `mercury` |

---

## Functionality

| Command | Behavior | Aliases |
|---|---|---|
| `build` | Runs the full pipeline. Accepts `--work-dir`, `--skip-fetch`/`--no-fetch`, `--skip-package`, `--clean`, `--mem-limit`, `--no-color`. | `bld make go compile` |
| `init` | Writes an example `rc.json` recipe to the positional target. | `gen template scaffold new` |
| `config` | Prints the active recipe configuration. | `cfg conf rc recipe` |
| `doctor` | Validates the host environment; exits 1 and lists missing required tools on failure, else prints the present tool set. | `chk check health preflight` |
| `info` | Prints the build plan for the active recipe (same fields as dry-run). Exits 1 if no valid recipe is found. | `plan preview show about` |
| `fetch` | Runs the source-fetch stage only. | `sync pull get clone` |
| `patch` | Applies the recipe patches. | `apply fix hotfix` |
| `pack` | Packages build outputs. With `--source PATH` packages an arbitrary directory (e.g. an extracted ROM); `--format FMT` overrides the recipe format. | `pkg archive bundle tar` |
| `extract` | Extracts a ROM archive (`--output/-o PATH` selects the target; default is the archive name without its suffix). Supports `.zip`, `.tar`, `.tar.gz`, `.tar.bz2`, `.tar.xz`, `.tgz`, `.7z`. | `unzip unpack inflate untar` |
| `repack` | Extracts a ROM archive into the product tree, runs the recipe's patches and hooks, and re-archives it. Positional `<destination>` optional (default `.`); `--format` overrides the output format. | `repackage rearchive rebundle mod` |
| `clean` | Requests a clean build. | `cls wipe purge` |
| `formats` | Lists supported output formats. | `fmt ext types` |
| `version` | Prints the version. | `ver verinfo verstr` |
| `env` | Prints the host environment report: Python version, CPU cores, total memory (GB), tools present, tools missing. | `environment sysinfo sysenv` |
| `log` | Prints the last 40 lines of the most recent `*-build.log` in the current directory, or in `--dir PATH` if given. Exits 1 if no log is found. | `logs tail journal` |
| `ccache` | Runs `ccache -s` and prints its statistics. Exits 1 if ccache is not installed. | `cache cc compilecache` |
| `jobs` | Prints the recommended job count for this host (`min(cores, 16)`, minimum 1). | `par cores jobcount` |
| `path` | Prints the canonical path of a given command path. With no argument, prints the current path. Exits 2 for an unknown path. | `which resolve trace` |
| `tree` | Prints the command tree. Accepts a positional depth or `--depth N`. | `map index browse` |
| `help` | Prints help for a command or path. | `assist ? manual` |
| `tier` | A 25-deep command chain. | `deep chain ladder` |
| `crush` | Opens the shell. | `sh console repl` |

---

## Cruine Shell: Crush

`cru crush` opens a REPL that navigates the command tree like a filesystem.
Commands resolve relative to the current tree path; the prompt shows the
current path (e.g. `cru/b>`).

```text
Cruine shell (crush) - 'help' for guidance, 'exit' to leave
cru> cd b
cru/b> bake
cru/b> cd bundle
cru/b/bundle> pwd
cru/b/bundle
cru/b/bundle> ..
cru/b>
```

### Built-ins

| Built-in | Behavior |
|---|---|
| `exit`, `quit` | Leave the shell |
| `cd [path]` | Change the current tree path; no argument returns to the root |
| `pwd` | Print the current path as `cru/<group>/<command>` |
| `ls` | List the children (commands and aliases) of the current node |
| `tree [path]` | Print a depth-limited subtree rooted here or at a path |
| `help [path]` | Print detailed help for the current node or a path |
| `clear` | Clear the terminal |

### Paths syntax

| Token | Meaning |
|---|---|
| `~`, `/` | Reset to the tree root |
| `.` | Current node (no-op) |
| `..` | Up one level (no-op at the root) |
| `child/child` | Slash-separated relative descent (e.g. `cd b/bundle`) |

Any line that is not a built-in is split with `shlex` and dispatched as a
tree command relative to the current path, so `bake` while sitting at
`cru/b>` runs `cru b/bake`.

On interactive terminals, readline provides tab completion over built-ins,
command names, aliases, and flags, plus persistent history in
`~/.cru_history` (written on exit).

```sh
cru crush                 # start at the root
cru crush a/analyze       # start inside a path
cru sh -p b/bundle        # same via -p/--path
cru sh --no-color         # plain prompt
```

---

## Flags

Available on every tree command:

| Option | Meaning |
|---|---|
| `-v, --verbose` | Verbose output |
| `-q, --quiet` | Suppress non-critical output |
| `-x, --debug` | Debug tracing |
| `-d, --dry-run` | Preview without executing |
| `-f, --format FMT` | Output format |
| `-o, --output PATH` | Output location |
| `-p, --path PATH` | Target path |
| `-n, --name NAME` | Name override |
| `-t, --target TARGET` | Target device or tree |
| `-m, --mode MODE` | Execution mode |
| `-c, --config FILE` | Configuration file |
| `-r, --recipe FILE` | Recipe file (`rc.json`) |
| `-j, --jobs N` | Parallel build jobs |
| `-l, --list` | List items |
| `-s, --silent` | Silent mode |
| `-e, --env KEY=VAL` | Environment override |

---

## Options

### Build variants

- `eng` — engineering build.
- `user` — production-like build.
- `userdebug` — user build with root and debug access (default).

### Clean vs incremental builds

Incremental builds are the default: a warm `out/` and ccache make rebuilds
fast. A clean build (`--clean` or `options.clean_build: true`) runs
`mka clean` (falling back to `make clean`) first.

### Parallels

Resolution order: `--jobs` flag, then recipe `parallel_jobs`, then the
host-derived recommendation.

### Memory limits

`--mem-limit MB` wraps the build in `ulimit -v` so a single compilation
cannot exhaust host memory.

### Extra make arguments

`options.extra_make_args` (e.g. `["-k", "WITH_DEXPREOPT=true"]`) are appended
verbatim to the `mka` invocation.

---

## Packaging

The artifact is written to the destination as
`<custom_name><format>`, or by default
`<project_name>-<codename><format>`.

| Format | Notes |
|---|---|
| `.zip` | Default |
| `.tar.gz` | Gzip-compressed tar |
| `.tar.bz2` | Bzip2-compressed tar |
| `.tar.xz` | XZ-compressed tar |
| `.tgz` | Alias for `.tar.gz` |
| `.7z` | 7-Zip archive (bundled library, CLI fallback) |
| `.img` | Raw image |
| `.iso` | ISO image (`pycdlib`, `mkisofs`/`genisoimage`/`xorriso` fallback) |
| `.tar` | Uncompressed tar |

Compression level is 0–9 (default 6). `obj` and `symbols` directories are
excluded by default. `cru formats` lists the supported formats.

---

## Patches and hooks

**Patches** apply out-of-tree source changes after fetching and before
building. Each is a normal diff applied with `git apply` at a configurable
strip level inside a target directory.

**Hooks** run shell commands at four fixed phases:

| Phase | Runs |
|---|---|
| `pre_fetch` | Before any source is fetched |
| `post_fetch` | After fetch, before patches |
| `pre_build` | After patches, before the build |
| `post_build` | After the build, before packaging |

Hooks are `sh -c` commands with an optional `workdir` relative to the
workspace.

---

## Variables

| Variable | Meaning |
|---|---|
| `CRU_JOBS` | Parallel job count; overrides recipe and CLI `--jobs` |
| `USE_CCACHE` | Set to `1` when ccache is enabled by the recipe |
| `CCACHE_EXEC` | Path to the ccache binary used during the build |
| `CCACHE_DIR` | ccache cache directory (default `~/.cache/ccache`) |
| `LC_ALL`, `LANG` | Forced to `C` during builds for stable output |

---

## Host prerequisites

`cru doctor` (and the pipeline automatically) checks for:

- Required: `git`, `bash`, `tar`, `python3`, `make`, `java`, `javac`. The
  pipeline aborts without all of them. A bare JRE (no `javac`) also fails —
  AOSP needs a full JDK. `repo` is not checked — Cruine syncs manifests
  natively.
- Build tools (warned, not fatal): `curl`, `rsync`, `lzip`, `xz`, `zstd`,
  `lz4`, `bc`, `bison`, `flex`, `openssl`, `git-lfs`, `schedtool`, `m4`,
  `perl`, `clang`, `clang++`, `gcc`, `g++`, `ninja`, `cmake`. Several are
  provided as prebuilts inside AOSP trees.
- Optional fallbacks: `ccache`, `7z`, `mkisofs`, `genisoimage`, `xorriso`,
  `unzip`. Missing tools degrade the corresponding feature (7-Zip/ISO
  packaging falls back to bundled libraries; ccache statistics reporting is
  skipped).

`cru doctor` also reports the detected libc profile and toolchain
(Cudane → musl/clang/clang++ with target triple
`<arch>-unknown-linux-musl`; glibc → gcc/g++ with `<arch>-unknown-linux-gnu`),
the detected JDK version, and hints when it does not match the usual AOSP
targets (JDK 8 for Android ≤ 10, JDK 11 for Android 11–12, JDK 17 for
Android 13+). `cru env` prints the full report: Python version, CPU cores,
total memory, libc/arch/triple, compiler pair, tools present, and tools
missing.

---

## Files produced

| Path | Contents |
|---|---|
| `rc.json` | The active recipe; discovered in the current directory |
| `<cwd>/<project_name>` | Default workspace (sources and `out/`) |
| `<destination>/<project_name>-build.log` | Full build log, written during the build |
| `<destination>/<archive>` | Final packaged artifact |
| `<workspace>/out/target/product/<codename>` | Extracted ROM tree in repack mode (also the normal build output location) |
| `~/.cache/ccache` | ccache cache (default) |
| `~/.cru_history` | Shell history for `cru crush` |

---

## Exit status

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Runtime error (missing recipe, validation failure, build failure, packaging failure, environment failure) |
| `2` | Usage error (unknown command, unknown option, unknown path) |
| `130` | Interrupted (SIGINT) |

---

## Workflows

### Fresh build

```sh
mkdir -p ~/builds/pocof3 && cd ~/builds/pocof3
cru init ./rc.json

# edit rc.json
cru info
cru /tmp/rom-out
```

### Rebuild with existing sources

```sh
cru /tmp/rom-out --skip-fetch -j 32
```

### Pre-flight validation

```sh
cru build --dry-run
cru doctor
```

### Stage-by-stage

```sh
cru fetch            # sources only
cru patch            # patches only
cru build --clean    # clean build only
cru pack             # package existing outputs
cru log --dir /var/log/rom
cru ccache
cru jobs
```

### Repack an existing ROM (recipe)

```sh
cd ~/builds/stock-mod
# rc.json sets "input": { "archive": "~/roms/stock.zip" }
#   and hooks that modify the extracted tree
cru repack ~/roms/stock.zip ./out --format .tar.gz
# equivalent: cru build ./out   (input.archive drives repack mode)
```

### Repack an existing ROM (manual)

```sh
cru extract ~/roms/stock.zip -o ./rom

# edit anything under ./rom/...
cru pack ./out --source ./rom --format .zip
```

### Local building

```sh
# rc.json uses file:// paths for the manifest and device trees
cru info              # verify the plan
cru ./rom-out --skip-fetch
```

### Shell init

```sh
cru crush
cru> tree 2
cru> cd b
cru/b> ls
cru/b> bundle
```

---

## Performance notes

- AOSP builds commonly require 200+ GB of free space. Cruine warns below
  10 GB free in the working directory.
- ccache reduces repeated-build time; set `ccache_size` to fit available
  disk.
- `--skip-fetch` avoids re-syncing the source tree on rebuilds.
- Compression cost: `.tar.xz` and `.7z` produce smaller archives at higher
  CPU cost; `.zip` and `.tar.gz` are faster. Level 6 is the default.

---

## Security

See `SECURITY.md` for the supported-versions and reporting policy.

- `hooks` execute arbitrary shell and `patches` are applied to sources;
  treat untrusted `rc.json` files as untrusted code.
- Archive extraction refuses members that resolve outside the destination
  directory (path-traversal protection).
- `LC_ALL`/`LANG` are forced to `C` during builds for deterministic tool
  output.
- Signing keys and credentials should not be committed into recipes; the
  `patches-hooks` example copies keys out of the workspace in a
  `post_build` hook.

---

## Documentation

- `docs/cru.1` — man page (bin).
- `docs/crush.1` — man page (shell).
- `docs/rc.json.5` — recipe format reference.
- `examples/` — adaptable recipes (real device, local sources, patches and
  hooks).
- `CONTRIBUTING.md` — development setup, quality gates, style.
- Build files (all share the `scripts/detect.sh` host-profile detector):
  `Makefile`/`env.mk`, `build.ninja`, `meson.build`, `scripts/cross.sh`,
  `toolchain.cmake`, `scripts/pkgconfig.sh`, `scripts/package.sh`,
  `packaging/cru.spec`. See the [Build system](#build-system) section.

Man pages install with `make install` (or `ninja install` /
`meson install`) under `$(PREFIX)/share/man`.

---

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install "./src[dev]"
make test      # .venv/bin/python -m pytest src/tests
make lint      # ruff check + ruff format --check on src/
make build     # standalone target/cru binary
```

Equivalent non-Make invocations: `ninja` (build), `meson setup build &&
meson compile -C build` (build), `ninja test`-style gates via
`.venv/bin/python -m pytest src/tests`.

The test suite includes an integration test that runs the real
`cru <destination>` pipeline against a synthetic tree (git clone, bash
build, zip packaging) and requires `git`/`bash`/`tar` on PATH.

---

## License

**MIT** ─ See [LICENSE](https://github.com/Mapuse/.github/blob/profile/LICENSE) for More Details.