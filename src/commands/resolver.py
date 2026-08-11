"""Command path resolution."""

from __future__ import annotations

from cruine.commands.flags import COMMON_FLAGS
from cruine.commands.model import Command, Flag, Resolution

__all__ = ["CommandResolver"]


class CommandResolver:
    def __init__(self, root: Command) -> None:
        self.root = root
        self._lookup: dict[Command, dict[str, Command]] = {}

    def index(self) -> CommandResolver:
        for node in self._walk(self.root):
            self._lookup[id(node)] = {}
            for child in node.children:
                self._lookup[id(node)][child.name] = child
                for alias in child.aliases:
                    self._lookup[id(node)].setdefault(alias, child)
        return self

    @staticmethod
    def _walk(root: Command):
        stack = [root]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(node.children)

    @staticmethod
    def _find_flag(node: Command, option: str) -> Flag | None:
        for flag in (*COMMON_FLAGS, *node.flags):
            if flag.short == option or flag.long == option:
                return flag
        return None

    def parse(self, argv: list[str]) -> Resolution:
        res = Resolution()
        node = self.root
        i = 0
        while i < len(argv):
            token = argv[i]
            if token in ("-h", "--help"):
                res.flags["help"] = True
                i += 1
                continue
            if token.startswith("-") and token != "-":
                option = token.split("=", 1)[0]
                flag = self._find_flag(node, option)
                if flag is None:
                    res.error = (
                        f"unknown option {option!r} for 'cru {' '.join(res.path) or '<root>'}'"
                    )
                    return res
                if flag.action == "store_true":
                    res.flags[flag.key] = True
                    i += 1
                    continue
                if "=" in token:
                    res.flags[flag.key] = token.split("=", 1)[1]
                    i += 1
                    continue
                if i + 1 >= len(argv):
                    res.error = f"option {option!r} requires a value"
                    return res
                res.flags[flag.key] = argv[i + 1]
                i += 2
                continue
            child = self._lookup[id(node)].get(token)
            if child is not None:
                res.path.append(child.name)
                res.tokens.append(token)
                node = child
                i += 1
                continue
            if node.positional is not None:
                res.values.append(token)
                i += 1
                continue
            res.error = (
                f"unknown command or argument {token!r} for 'cru {' '.join(res.path) or '<root>'}'"
            )
            return res
        res.node = node
        return res
