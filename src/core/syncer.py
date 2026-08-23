"""Native multi-repo manifest sync engine.

A complete, standalone replacement for the AOSP ``repo`` tool and every other
manifest-sync wrapper. Cruine parses AOSP-style manifest XML directly and
syncs each active project with plain ``git`` — no ``repo`` binary, no
external manifest tool, and no assumptions about git hosts, URL schemes, or
revision names.

Anything ``git`` can clone, Cruine can sync:

* any URL form — ``https``, ``ssh``, ``git``, ``file://``, scp-style
  ``git@host:path``, or a plain local path;
* any revision — branch names, tags, ``refs/heads/*`` / ``refs/tags/*``
  prefixes, or raw SHA-1 commit ids;
* any AOSP-family manifest — LineageOS, AOSP, crDroid, PixelOS, EvolutionX,
  ArrowOS, and every other ROM that uses the ``repo`` manifest format.

State lives under ``<workspace>/.cruine``: the manifest clone in
``.cruine/manifests``, extra projects in ``.cruine/local_manifests/*.xml``
(``.repo/local_manifests`` is honoured too for existing workflows), and a
small JSON state file that lets unchanged projects skip the network entirely.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from cruine.models.recipe import RecipeSchema
from cruine.utils.logger import log
from cruine.utils.runner import CommandError, run_retry
from cruine.utils.urls import localize_url, normalize_url

__all__ = [
    "ManifestParser",
    "ManifestProject",
    "ManifestRemote",
    "ManifestSyncer",
    "ParsedManifest",
    "SyncError",
    "active_projects",
    "is_absolute_ref",
    "ref_name",
]


class SyncError(RuntimeError):
    """Raised when manifest parsing or project sync fails."""


@dataclass
class ManifestRemote:
    name: str
    fetch: str = ""
    revision: str | None = None
    alias: str | None = None


@dataclass
class ManifestProject:
    name: str
    path: str
    remote: str | None = None
    revision: str | None = None
    groups: str | None = None
    depth: int | None = None
    copyfiles: list[tuple[str, str]] = field(default_factory=list)
    linkfiles: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class ParsedManifest:
    remotes: dict[str, ManifestRemote] = field(default_factory=dict)
    default_remote: str | None = None
    default_revision: str | None = None
    projects: list[ManifestProject] = field(default_factory=list)
    removed: set[str] = field(default_factory=set)

    def merge(self, other: ParsedManifest) -> None:
        """Merge a local/extended manifest into this one."""
        self.remotes.update(other.remotes)
        self.projects.extend(other.projects)
        self.removed.update(other.removed)
        if other.default_remote:
            self.default_remote = other.default_remote
        if other.default_revision:
            self.default_revision = other.default_revision

    def resolve_url(self, project: ManifestProject, manifest_url: str) -> str:
        """Build the clone URL for a project from its remote and name.

        Relative fetch values (``..``, ``./``, ``../..``) resolve against the
        manifest repository URL exactly like the AOSP tools do: the manifest
        URL is treated as a file, so ``fetch=".."`` points at its parent.
        Absolute URLs (https, ssh, git, ``file://``, scp-style, ``/abs/path``)
        are used verbatim — any host works.
        """
        remote_name = project.remote or self.default_remote
        if remote_name is None:
            raise SyncError(f"project {project.name!r} has no remote")
        remote = self.remotes.get(remote_name)
        if remote is None:
            raise SyncError(f"unknown remote {remote_name!r} for project {project.name!r}")
        fetch = normalize_url(remote.fetch or "")
        if fetch and not _is_absolute_fetch(fetch):
            fetch = urllib.parse.urljoin(manifest_url, fetch).rstrip("/")
        base = fetch.rstrip("/")
        return f"{base}/{project.name}" if base else project.name

    def revision_for(self, project: ManifestProject) -> str:
        """Resolve a project revision: project > remote > default."""
        if project.revision:
            return project.revision
        if project.remote:
            remote = self.remotes.get(project.remote)
            if remote and remote.revision:
                return remote.revision
        if self.default_remote:
            remote = self.remotes.get(self.default_remote)
            if remote and remote.revision:
                return remote.revision
        if self.default_revision:
            return self.default_revision
        raise SyncError(f"project {project.name!r} has no revision")


def _is_absolute_fetch(fetch: str) -> bool:
    return (
        "://" in fetch
        or fetch.startswith("//")
        or fetch.startswith("/")
        or fetch.startswith("~")
        or "@" in fetch.split(":", 1)[0]
    )


def ref_name(revision: str) -> str:
    """Strip a ``refs/heads/`` / ``refs/tags/`` prefix to a plain ref name."""
    for prefix in ("refs/heads/", "refs/tags/"):
        if revision.startswith(prefix):
            return revision[len(prefix) :]
    return revision


def is_absolute_ref(revision: str) -> bool:
    """True for a raw 40-hex SHA-1 (an immutable, fetchable revision)."""
    return len(revision) == 40 and all(c in "0123456789abcdefABCDEF" for c in revision)


def active_projects(
    manifest: ParsedManifest,
    requested_groups: list[str] | None = None,
) -> list[ManifestProject]:
    """Projects to sync: not removed, and matching the requested groups.

    With no explicit groups, the standard ``default`` group is synced: every
    project except those marked ``notdefault`` (mirroring ``repo``).
    """
    groups = requested_groups if requested_groups else ["default"]
    active: list[ManifestProject] = []
    for project in manifest.projects:
        if project.name in manifest.removed:
            continue
        if not _matches_groups(project.groups, groups):
            continue
        active.append(project)
    return active


def _matches_groups(project_groups: str | None, requested: list[str]) -> bool:
    if not project_groups:
        if "all" in requested:
            return True
        if "default" in requested:
            return True
        return all(g.startswith("-") for g in requested)
    members = set(project_groups.replace(",", " ").split())
    members.add("all")
    if "notdefault" not in members:
        members.add("default")
    for group in requested:
        if group.startswith("-"):
            if group[1:] in members:
                return False
        elif group in members:
            return True
    return False


class ManifestParser:
    """Parse an AOSP ``repo`` manifest document into :class:`ParsedManifest`.

    Supports remotes, defaults, projects (with copyfile/linkfile), groups,
    ``remove-project``, ``extend-project``, ``include`` and embedded
    ``submanifest`` projects. Unknown or tool-specific elements
    (``superproject``, ``manifest-server``, ``repo-hooks``, ...) are ignored,
    so any ROM manifest parses cleanly.
    """

    def __init__(self, manifest_dir: Path) -> None:
        self.manifest_dir = Path(manifest_dir)
        self.remotes: dict[str, ManifestRemote] = {}
        self.default_remote: str | None = None
        self.default_revision: str | None = None
        self.projects: list[ManifestProject] = []
        self.removed: set[str] = set()
        self._extensions: list[tuple[str, ET.Element]] = []

    def parse(self, text: str) -> ParsedManifest:
        text = text.lstrip("\ufeff")
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise SyncError(f"invalid manifest XML: {exc}") from exc
        self._walk(root)
        self._apply_extensions()
        return ParsedManifest(
            remotes=self.remotes,
            default_remote=self.default_remote,
            default_revision=self.default_revision,
            projects=self.projects,
            removed=self.removed,
        )

    def _walk(self, node: ET.Element, path_prefix: str = "") -> None:
        for child in node:
            tag = child.tag
            if tag == "remote":
                name = child.get("name")
                if name:
                    remote = ManifestRemote(
                        name=name,
                        fetch=child.get("fetch", ""),
                        revision=child.get("revision"),
                        alias=child.get("alias"),
                    )
                    self.remotes[name] = remote
                    if remote.alias:
                        self.remotes[remote.alias] = remote
            elif tag == "default":
                if child.get("remote"):
                    self.default_remote = child.get("remote")
                if child.get("revision"):
                    self.default_revision = child.get("revision")
            elif tag == "project":
                project = self._parse_project(child, path_prefix)
                if project is not None:
                    self.projects.append(project)
            elif tag == "remove-project":
                name = child.get("name")
                if name:
                    self.removed.add(name)
            elif tag == "extend-project":
                name = child.get("name")
                if name:
                    self._extensions.append((name, child))
            elif tag == "include":
                self._parse_include(child, path_prefix)
            elif tag == "submanifest":
                sub_path = child.get("path")
                prefix = f"{path_prefix}{sub_path}/" if sub_path else path_prefix
                self._walk(child, prefix)
            elif tag in (
                "annotate",
                "contactinfo",
                "manifest-server",
                "notice",
                "repo-hooks",
                "superproject",
            ):
                continue
            else:
                log.debug(f"ignoring unknown manifest element <{tag}>")

    def _parse_project(self, node: ET.Element, path_prefix: str = "") -> ManifestProject | None:
        name = node.get("name")
        if not name:
            return None
        path = node.get("path") or name
        if path_prefix:
            path = f"{path_prefix}{path.strip('/')}"
        project = ManifestProject(
            name=name,
            path=path,
            remote=node.get("remote"),
            revision=node.get("revision"),
            groups=node.get("groups"),
            depth=_positive_int(node.get("clone-depth") or node.get("depth")),
        )
        for sub in node:
            if sub.tag == "copyfile":
                project.copyfiles.append((sub.get("src"), sub.get("dest")))
            elif sub.tag == "linkfile":
                project.linkfiles.append((sub.get("src"), sub.get("dest")))
        return project

    def _apply_extensions(self) -> None:
        for name, node in self._extensions:
            for project in self.projects:
                if project.name != name:
                    continue
                if node.get("path"):
                    project.path = node.get("path")
                if node.get("remote"):
                    project.remote = node.get("remote")
                if node.get("revision"):
                    project.revision = node.get("revision")

    def _parse_include(self, node: ET.Element, path_prefix: str = "") -> None:
        name = node.get("name")
        if not name:
            raise SyncError("include element missing name")
        path = (self.manifest_dir / name).resolve()
        if not path.is_file():
            raise SyncError(f"included manifest not found: {name}")
        try:
            root = ET.fromstring(path.read_text(encoding="utf-8").lstrip("\ufeff"))
        except ET.ParseError as exc:
            raise SyncError(f"invalid included manifest {name}: {exc}") from exc
        self._walk(root, path_prefix)


def _positive_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if number > 0 else None


class ManifestSyncer:
    """Native ``repo``-free manifest clone and multi-project sync engine."""

    STATE_DIR = ".cruine"
    MANIFESTS_DIR = "manifests"
    LOCAL_MANIFESTS_DIR = "local_manifests"
    STATE_FILE = "state.json"
    MANIFEST_FILES = ("default.xml", "manifest.xml")

    def __init__(
        self,
        recipe: RecipeSchema,
        workspace: Path,
        jobs: int | None = None,
    ) -> None:
        self.recipe = recipe
        self.workspace = Path(workspace)
        self.jobs = jobs or recipe.options.parallel_jobs or (os.cpu_count() or 1)
        self.state_dir = self.workspace / self.STATE_DIR
        self.manifests_dir = self.state_dir / self.MANIFESTS_DIR
        self.local_manifests_dir = self.state_dir / self.LOCAL_MANIFESTS_DIR
        self._state: dict[str, dict[str, str]] = self._load_state()

    # -- public API -------------------------------------------------------

    def sync(self) -> int:
        """Clone/update the manifest repo and sync every active project.

        Returns the number of projects synced.
        """
        self.workspace.mkdir(parents=True, exist_ok=True)
        manifest_url = self._ensure_manifest_repo()
        parsed = self._load_manifest()
        projects = active_projects(parsed, self._requested_groups())
        log.info(f"Manifest defines {len(parsed.projects)} project(s); syncing {len(projects)}")
        self._sync_projects(projects, parsed, manifest_url)
        self._save_state()
        log.success(f"Source manifest sync complete: {len(projects)} project(s)")
        return len(projects)

    # -- manifest repo ----------------------------------------------------

    def _ensure_manifest_repo(self) -> str:
        """Clone or update the manifest repository; return its URL for fetch resolution."""
        manifest_url = normalize_url(self.recipe.rom.source)
        if (self.manifests_dir / ".git").exists():
            if self._unchanged(self.manifests_dir, manifest_url, self.recipe.rom.branch):
                log.info("Manifest repo unchanged -> skipping fetch")
            else:
                log.info("Manifest repo already present -> updating")
                run_retry(
                    [
                        "git",
                        "-C",
                        str(self.manifests_dir),
                        "fetch",
                        "--tags",
                        "--prune",
                        "-f",
                        "origin",
                    ],
                    "manifest fetch",
                )
                self._checkout_revision(
                    self.manifests_dir, manifest_url, self.recipe.rom.branch, fresh=False
                )
                self._mark_synced(self.manifests_dir, manifest_url, self.recipe.rom.branch)
        else:
            self.manifests_dir.parent.mkdir(parents=True, exist_ok=True)
            log.info(f"Cloning manifest repo: {manifest_url} ({self.recipe.rom.branch})")
            clone = ["git", "clone"]
            if self.recipe.rom.depth:
                clone += ["--depth", str(self.recipe.rom.depth)]
            clone += [localize_url(manifest_url), str(self.manifests_dir)]
            run_retry(clone, "manifest clone", retry_cleanup_path=self.manifests_dir)
            self._checkout_revision(
                self.manifests_dir, manifest_url, self.recipe.rom.branch, fresh=True
            )
            self._mark_synced(self.manifests_dir, manifest_url, self.recipe.rom.branch)
        return manifest_url

    def _load_manifest(self) -> ParsedManifest:
        manifest_file = self._find_manifest_file()
        parser = ManifestParser(self.manifests_dir)
        parsed = parser.parse(manifest_file.read_text(encoding="utf-8"))
        for local_dir in (
            self.local_manifests_dir,
            self.workspace / ".repo" / "local_manifests",
        ):
            if local_dir.is_dir():
                for extra in sorted(local_dir.glob("*.xml")):
                    log.info(f"Merging local manifest: {extra}")
                    extra_parser = ManifestParser(local_dir)
                    parsed.merge(extra_parser.parse(extra.read_text(encoding="utf-8")))
        return parsed

    def _find_manifest_file(self) -> Path:
        name = self.recipe.rom.manifest
        if name:
            path = self.manifests_dir / name
            if path.is_file():
                return path
            raise SyncError(f"manifest file not found: {name} in {self.manifests_dir}")
        for candidate in self.MANIFEST_FILES:
            path = self.manifests_dir / candidate
            if path.is_file():
                return path
        raise SyncError(
            f"no manifest file ({', '.join(self.MANIFEST_FILES)}) in {self.manifests_dir}"
        )

    # -- project sync -----------------------------------------------------

    def _sync_projects(
        self,
        projects: list[ManifestProject],
        parsed: ParsedManifest,
        manifest_url: str,
    ) -> None:
        if not projects:
            return
        failures: list[str] = []
        workers = max(1, min(self.jobs, len(projects)))

        def run(project: ManifestProject) -> None:
            try:
                self._sync_project(project, parsed, manifest_url)
            except Exception as exc:
                failures.append(f"{project.path}: {exc}")

        if workers == 1:
            for project in projects:
                run(project)
        else:
            log.info(f"Syncing {len(projects)} project(s) with {workers} workers")
            with ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(run, projects))
        if failures:
            detail = "\n".join(f"  - {failure}" for failure in failures)
            raise SyncError(f"sync failed for {len(failures)} project(s):\n{detail}")

    def _sync_project(
        self,
        project: ManifestProject,
        parsed: ParsedManifest,
        manifest_url: str,
    ) -> None:
        url = localize_url(parsed.resolve_url(project, manifest_url))
        revision = ref_name(parsed.revision_for(project))
        dest = self._safe_destination(project.path)

        if self._unchanged(dest, url, revision):
            log.info(f"{project.path} unchanged -> skipping")
            return

        if dest.exists() and not (dest / ".git").exists():
            log.warning(f"Removing partial clone: {dest}")
            shutil.rmtree(dest)

        fresh = not (dest / ".git").exists()
        if fresh:
            dest.parent.mkdir(parents=True, exist_ok=True)
            log.info(f"Cloning {project.path} <- {url} @ {revision}")
            clone = ["git", "clone"]
            if project.depth or self.recipe.rom.depth:
                clone += ["--depth", str(project.depth or self.recipe.rom.depth)]
            clone += [url, str(dest)]
            run_retry(clone, f"clone {project.path}", retry_cleanup_path=dest)
        else:
            log.info(f"Updating {project.path} <- {url} @ {revision}")
            run_retry(
                ["git", "-C", str(dest), "fetch", "--tags", "--prune", "-f", "origin"],
                f"fetch {project.path}",
            )

        self._checkout_revision(dest, url, revision, fresh=fresh)
        self._apply_file_ops(project, dest)
        self._mark_synced(dest, url, revision)

    def _checkout_revision(self, dest: Path, url: str, revision: str, fresh: bool = False) -> None:
        """Check out ``revision`` at the freshly fetched upstream commit.

        A fresh clone can check out the requested ref directly (the checkout
        is already at the upstream tip). An existing clone is fetched first
        and then hard-reset to ``FETCH_HEAD`` so a branch revision never
        leaves a stale local branch checked out — mirroring ``repo sync``.
        """
        if fresh:
            try:
                run_retry(
                    ["git", "-C", str(dest), "checkout", "-f", revision],
                    f"checkout {revision} in {dest.name}",
                )
            except CommandError:
                pass
            else:
                return
        try:
            run_retry(
                ["git", "-C", str(dest), "fetch", "-f", "origin", revision],
                f"fetch {revision} in {dest.name}",
            )
        except CommandError:
            run_retry(
                ["git", "-C", str(dest), "fetch", "--tags", "-f", "origin"],
                f"fetch refs in {dest.name}",
            )
        if is_absolute_ref(revision):
            run_retry(
                ["git", "-C", str(dest), "checkout", "-f", revision],
                f"checkout {revision} in {dest.name}",
            )
        else:
            run_retry(
                ["git", "-C", str(dest), "reset", "--hard", "FETCH_HEAD"],
                f"checkout {revision} in {dest.name}",
            )

    def _apply_file_ops(self, project: ManifestProject, dest: Path) -> None:
        for src, dst in project.copyfiles:
            src_path, dst_path = dest / src, dest / dst
            if not src_path.is_file():
                log.warning(f"copyfile source missing: {project.path}/{src}")
                continue
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)
            log.info(f"copyfile: {src} -> {dst}")
        for src, dst in project.linkfiles:
            dst_path = dest / dst
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            if dst_path.is_symlink() or dst_path.exists():
                dst_path.unlink()
            target = os.path.relpath(dest / src, dst_path.parent)
            os.symlink(target, dst_path)
            log.info(f"linkfile: {dst} -> {src}")

    def _safe_destination(self, project_path: str) -> Path:
        if project_path.startswith(("/", "~")) or ".." in Path(project_path).parts:
            raise SyncError(f"unsafe project path: {project_path!r}")
        path = (self.workspace / project_path).resolve()
        root = self.workspace.resolve()
        if path != root and root not in path.parents:
            raise SyncError(f"project path escapes workspace: {project_path!r}")
        return path

    # -- fast path: skip unchanged projects ------------------------------

    def _unchanged(self, dest: Path, url: str, revision: str) -> bool:
        """True when a project is already checked out at the requested commit."""
        entry = self._state.get(str(dest))
        if not entry or entry.get("url") != url or entry.get("revision") != revision:
            return False
        if not (dest / ".git").exists():
            return False
        head = self._capture(["git", "-C", str(dest), "rev-parse", "HEAD"])
        if head is None:
            return False
        if is_absolute_ref(revision):
            return head == revision
        tip = self._ls_remote_tip(url, revision)
        return tip is not None and head == tip

    def _ls_remote_tip(self, url: str, revision: str) -> str | None:
        try:
            proc = subprocess.run(
                ["git", "ls-remote", localize_url(url), revision],
                capture_output=True,
                text=True,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if proc.returncode != 0:
            return None
        lines = [line for line in proc.stdout.splitlines() if line]
        return lines[0].split("\t")[0] if lines else None

    def _capture(self, command: list[str]) -> str | None:
        try:
            proc = subprocess.run(list(command), capture_output=True, text=True, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        if proc.returncode != 0:
            return None
        return proc.stdout.strip()

    def _mark_synced(self, dest: Path, url: str, revision: str) -> None:
        self._state[str(dest)] = {"url": url, "revision": revision}

    def _load_state(self) -> dict[str, dict[str, str]]:
        path = self.state_dir / self.STATE_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.state_dir / self.STATE_FILE
        path.write_text(json.dumps(self._state, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _requested_groups(self) -> list[str] | None:
        groups = self.recipe.rom.groups
        if not groups:
            return None
        return [g for g in groups.replace(",", " ").split() if g]
