"""Top-level command dispatch."""

from __future__ import annotations

import sys

from cruine.commands.handlers import HANDLERS
from cruine.commands.tree import RESOLVER, TREE, _print_node, _print_tree

__all__ = ["dispatch"]


def dispatch(argv: list[str]) -> int:
    res = RESOLVER.parse(argv)
    if res.error:
        print(f"cru: {res.error}", file=sys.stderr)
        print("Try 'cru help' or 'cru tree'.", file=sys.stderr)
        return 2
    node = res.node
    if node is None:
        _print_tree(TREE, 0, 3)
        return 2
    if res.flags.get("help"):
        _print_node(node, res.path)
        return 0
    if node.is_group:
        _print_node(node, res.path)
        return 0
    handler = HANDLERS.get(node.handler)
    if handler is None:
        _print_node(node, res.path)
        return 0
    try:
        return handler(res)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except (FileNotFoundError, ValueError, OSError, RuntimeError) as exc:
        print(f"cru: {exc}", file=sys.stderr)
        return 1
