"""Cruine build-pipeline engines."""

from __future__ import annotations

from cruine.core.environment import EnvironmentManager
from cruine.core.executor import BuildExecutor
from cruine.core.fetcher import SourceFetcher
from cruine.core.packager import OutputPackager
from cruine.core.patcher import Patcher
from cruine.core.syncer import (
    ManifestParser,
    ManifestProject,
    ManifestRemote,
    ManifestSyncer,
    ParsedManifest,
    SyncError,
)

__all__ = [
    "BuildExecutor",
    "EnvironmentManager",
    "ManifestParser",
    "ManifestProject",
    "ManifestRemote",
    "ManifestSyncer",
    "OutputPackager",
    "ParsedManifest",
    "Patcher",
    "SourceFetcher",
    "SyncError",
]
