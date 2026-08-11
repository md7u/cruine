"""Tests for the command tree, resolver, and dispatch."""

from __future__ import annotations

import json

from cruine.commands import (
    RESOLVER,
    TOP_INDEX,
    TREE,
    ChainBuilder,
    Command,
    CommandBuilder,
    GroupBuilder,
    SubBuilder,
    dispatch,
    is_top_command,
)


def test_is_top_command() -> None:
    assert is_top_command("build")
    assert is_top_command("version")
    assert not is_top_command("/tmp/out")
    assert not is_top_command("--help")


def test_alias_resolves_to_same_node() -> None:
    assert TOP_INDEX["bld"] is TOP_INDEX["build"]
    assert TOP_INDEX["go"] is TOP_INDEX["build"]


def test_dispatch_version(capsys) -> None:
    assert dispatch(["version"]) == 0
    assert "Cruine" in capsys.readouterr().out


def test_dispatch_formats(capsys) -> None:
    assert dispatch(["formats"]) == 0
    assert ".zip" in capsys.readouterr().out


def test_dispatch_unknown_command(capsys) -> None:
    assert dispatch(["bogus"]) == 2
    assert "unknown command" in capsys.readouterr().err


def test_dispatch_log_tails_newest_by_mtime(tmp_path, capsys) -> None:
    import os

    old = tmp_path / "a-build.log"
    new = tmp_path / "b-build.log"
    old.write_text("OLD LOG\n" * 50, encoding="utf-8")
    new.write_text("NEW LOG\n" * 50, encoding="utf-8")
    os.utime(old, (1000.0, 1000.0))
    os.utime(new, (2000.0, 2000.0))
    assert dispatch(["log", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "b-build.log" in out
    assert "NEW LOG" in out
    assert "OLD LOG" not in out


def test_dispatch_build_help(capsys) -> None:
    assert dispatch(["build", "--help"]) == 0
    assert "cru build" in capsys.readouterr().out


def test_resolver_parse_build_flags() -> None:
    res = RESOLVER.parse(["build", "--dry-run", "-j", "16", "--no-fetch"])
    assert res.node is not None and res.node.handler == "build"
    assert res.flags.get("dry-run") is True
    assert res.flags.get("no-fetch") is True
    assert res.flags.get("jobs") == "16"


def test_resolver_parse_positional() -> None:
    res = RESOLVER.parse(["build", "/tmp/out"])
    assert res.values == ["/tmp/out"]


def test_resolver_rejects_unknown_flag() -> None:
    res = RESOLVER.parse(["build", "--bogus"])
    assert res.error is not None


def test_resolver_rejects_unknown_subcommand() -> None:
    res = RESOLVER.parse(["a", "not-a-child"])
    assert res.error is not None


def test_group_node_displays_children(capsys) -> None:
    assert dispatch(["a"]) == 0
    out = capsys.readouterr().out
    assert "analyze" in out


def test_tree_has_groups_and_functionals() -> None:
    names = {child.name for child in TREE.children}
    assert {"a", "z", "A", "Z"} <= names
    assert {"build", "init", "doctor", "help", "crush"} <= names


def test_tree_parse_uses_recipes(capsys, monkeypatch, tmp_path) -> None:
    recipe = {
        "project_name": "TestROM",
        "rom": {
            "source": "https://example.com/android.git",
            "branch": "b",
            "lunch_prefix": "test",
            "build_target": "bacon",
        },
        "device": {
            "codename": "testdevice",
            "repositories": [
                {"type": "device", "url": "https://e.com/d.git", "target_path": "device/x/a"}
            ],
        },
    }
    (tmp_path / "rc.json").write_text(json.dumps(recipe), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert dispatch(["info"]) == 0
    assert "TestROM" in capsys.readouterr().out


def test_dispatch_config_shows_effective_settings(capsys, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CRUINE_CONFIG", str(tmp_path / "missing.toml"))
    assert dispatch(["config"]) == 0
    out = capsys.readouterr().out
    assert "log.format" in out
    assert "[{ts}]" in out


def test_dispatch_config_init_writes_template(capsys, monkeypatch, tmp_path) -> None:
    target = tmp_path / "cfg.toml"
    monkeypatch.setenv("CRUINE_CONFIG", str(target))
    assert dispatch(["config", "init"]) == 0
    assert "config written to" in capsys.readouterr().out
    assert "[log.statuses]" in target.read_text(encoding="utf-8")


def test_dispatch_config_init_dir_flag(capsys, monkeypatch, tmp_path) -> None:
    dest = tmp_path / "cfgdir"
    monkeypatch.setenv("CRUINE_CONFIG", str(tmp_path / "unused.toml"))
    assert dispatch(["config", "init", "--dir", str(dest)]) == 0
    assert "config written to" in capsys.readouterr().out
    written = dest / "config.toml"
    assert "[log.statuses]" in written.read_text(encoding="utf-8")


def test_dispatch_config_reload(capsys, monkeypatch, tmp_path) -> None:
    import io

    from cruine.utils.logger import log

    cfg = tmp_path / "config.toml"
    cfg.write_text('[log]\nformat = "[{status}] {message}"\n', encoding="utf-8")
    monkeypatch.setenv("CRUINE_CONFIG", str(cfg))
    stream = io.StringIO()
    monkeypatch.setattr(log, "stream", stream)
    monkeypatch.setattr(log, "no_color", True)
    assert dispatch(["config", "reload"]) == 0
    assert "config reloaded" in capsys.readouterr().out
    log.info("after")
    assert stream.getvalue().strip() == "[Info] after"


def test_dispatch_config_path(capsys, monkeypatch, tmp_path) -> None:
    target = tmp_path / "cfg.toml"
    monkeypatch.setenv("CRUINE_CONFIG", str(target))
    assert dispatch(["config", "path"]) == 0
    assert capsys.readouterr().out.strip() == str(target)


def test_dispatch_config_bad_action(capsys) -> None:
    assert dispatch(["config", "bogus"]) == 2
    assert "unknown config action" in capsys.readouterr().err


def test_command_builder_builds_node() -> None:
    node = (
        CommandBuilder("probe", "probe the device")
        .aliases("scan", "ping", "p")
        .handler("echo")
        .positional("target")
        .build()
    )
    assert node.name == "probe"
    assert node.aliases == ("scan", "ping", "p")
    assert node.handler == "echo"
    assert node.positional == "target"


def test_command_builder_attaches_parent() -> None:
    parent = Command("bucket", "bucket command")
    child = CommandBuilder("leaf", "leaf command").handler("echo").build(parent)
    assert child.parent is parent


def test_sub_builder_nests_levels() -> None:
    parent = Command("root", "root command")
    subs = SubBuilder(seed=0).levels(3).build(parent)
    assert len(subs) == 2
    assert all(child.parent is parent for child in subs)
    assert all(child.children for child in subs)
    assert all(grand.children for child in subs for grand in child.children)


def test_sub_builder_mixed_aliases() -> None:
    parent = Command("root", "root command")
    for node in SubBuilder(seed=0).levels(2).build(parent):
        assert len(node.aliases) >= 3


def test_chain_builder_builds_path() -> None:
    chain = ChainBuilder(("one", "two", "three"), seed=0).build()
    assert chain.name == "one"
    assert chain.children[0].name == "two"
    assert chain.children[0].children[0].name == "three"
    assert chain.children[0].parent is chain


def test_group_builder_has_words_and_chain() -> None:
    group = GroupBuilder("q", "query", "query qemu quick quiet", seed=3).build()
    assert group.name == "q"
    assert group.children[0].name == "query"
    assert group.children[-1].help.startswith("deep level")
