"""Cruine CLI command tree: alphabet groups, aliases, flags, deep chains."""

from __future__ import annotations

from cruine.commands.builders import (
    ChainBuilder,
    CommandBuilder,
    GroupBuilder,
    SubBuilder,
    _build_tree,
)
from cruine.commands.dispatch import dispatch
from cruine.commands.flags import COMMON_FLAGS
from cruine.commands.model import Command, Flag, Resolution
from cruine.commands.tree import (
    RESOLVER,
    TOP_INDEX,
    TREE,
    _find_by_path,
    _full_path,
    _print_node,
    _print_tree,
    is_top_command,
)

__all__ = [
    "COMMON_FLAGS",
    "RESOLVER",
    "TOP_INDEX",
    "TREE",
    "ChainBuilder",
    "Command",
    "CommandBuilder",
    "Flag",
    "GroupBuilder",
    "Resolution",
    "SubBuilder",
    "_build_tree",
    "_find_by_path",
    "_full_path",
    "_print_node",
    "_print_tree",
    "dispatch",
    "is_top_command",
]
