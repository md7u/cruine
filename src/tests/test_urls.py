"""Tests for source URL and archive-name helpers."""

from __future__ import annotations

from cruine.utils.urls import localize_url, strip_archive_suffix


def test_localize_file_url() -> None:
    assert localize_url("file:///home/m/rom") == "/home/m/rom"
    assert localize_url("file://rel/path") == "rel/path"
    assert localize_url("file://") == ""
    assert localize_url("https://example.com/a.git") == "https://example.com/a.git"
    assert localize_url("git@github.com:org/repo.git") == "git@github.com:org/repo.git"
    assert localize_url("/plain/path") == "/plain/path"


def test_strip_archive_suffix() -> None:
    assert strip_archive_suffix("LineageOS.tar.gz") == "LineageOS"
    assert strip_archive_suffix("rom.tar.xz") == "rom"
    assert strip_archive_suffix("bundle.tgz") == "bundle"
    assert strip_archive_suffix("rom.zip") == "rom"
    assert strip_archive_suffix("archive.7z") == "archive"
    assert strip_archive_suffix("plain") == "plain"
