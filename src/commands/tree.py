"""Root tree, resolver instance, and tree printing helpers."""

from __future__ import annotations

from cruine.commands.builders import _build_tree
from cruine.commands.model import Command
from cruine.commands.resolver import CommandResolver

__all__ = [
    "RESOLVER",
    "TOP_INDEX",
    "TREE",
    "_find_by_path",
    "_full_path",
    "_print_node",
    "_print_tree",
    "is_top_command",
]

TREE = _build_tree()
RESOLVER = CommandResolver(TREE).index()

TOP_INDEX: dict[str, Command] = {}
for _child in TREE.children:
    TOP_INDEX[_child.name] = _child
    for _alias in _child.aliases:
        TOP_INDEX.setdefault(_alias, _child)


def is_top_command(token: str) -> bool:
    return token in TOP_INDEX


def _print_node(node: Command, path: list[str]) -> None:
    display_path = " ".join(path) or node.name
    print(f"{node.name} - {node.help}")
    print(f"path    : cru {display_path}")
    print(f"aliases : {', '.join(node.aliases) if node.aliases else '(none)'}")
    if node.positional:
        print(f"arg     : <{node.positional}>")
    if node.flags:
        print("flags   :")
        for flag in node.flags:
            print(f"  {flag.display:<24} {flag.help}")
    print(
        "common  : -v/--verbose -q/--quiet -d/--dry-run -f/--format "
        "-o/--output -r/--recipe -j/--jobs ..."
    )
    if node.children:
        print("children:")
        for child in node.children:
            preview = ", ".join(child.aliases[:3]) or "-"
            print(f"  {child.name:<12} ({preview}) {child.help}")


def _print_tree(node: Command, depth: int, max_depth: int) -> None:
    for child in node.children:
        preview = ", ".join(child.aliases[:3]) or "-"
        print(f"{'  ' * depth}{child.name}  [{preview}]  {child.help}")
        if child.children and depth + 1 < max_depth:
            _print_tree(child, depth + 1, max_depth)


def _find_by_path(tokens: list[str]) -> Command | None:
    node = TREE
    for token in tokens:
        child = RESOLVER._lookup[id(node)].get(token)
        if child is None:
            return None
        node = child
    return node


def _full_path(node: Command) -> list[str]:
    parts: list[str] = []
    current: Command | None = node
    while current is not None and current is not TREE:
        parts.append(current.name)
        current = current.parent
    return list(reversed(parts))
