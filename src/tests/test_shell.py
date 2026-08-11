"""Tests for the interactive shell."""

from __future__ import annotations

from cruine.shell import Repl


def test_resolve_relative_path() -> None:
    node = Repl()._resolve(["a", "analyze"])
    assert node is not None
    assert node.name == "analyze"


def test_resolve_unknown_returns_none() -> None:
    assert Repl()._resolve(["notacommand"]) is None


def test_start_path_sets_path() -> None:
    repl = Repl(start_path="a/analyze")
    assert repl.path == ["a", "analyze"]


def test_cd_changes_path(capsys) -> None:
    repl = Repl()
    repl._cmd_cd(["a"])
    assert repl.path == ["a"]
    repl._cmd_cd([".."])
    assert repl.path == []
    repl._cmd_cd(["a", "analyze"])
    assert repl.path == ["a", "analyze"]


def test_cd_rejects_leaf(capsys) -> None:
    repl = Repl()
    repl._cmd_cd(["build"])
    assert repl.path == []


def test_candidates_include_children() -> None:
    candidates = Repl()._candidates("")
    assert "build" in candidates
    assert "version" in candidates
    assert "cd" in candidates
    assert "exit" in candidates


def test_builtin_pwd(capsys) -> None:
    repl = Repl(start_path="a")
    assert repl._builtin("pwd") is True
    assert capsys.readouterr().out.strip() == "cru/a"


def test_builtin_exit() -> None:
    repl = Repl()
    assert repl._builtin("exit") is True
    assert repl._exit
