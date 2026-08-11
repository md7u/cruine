"""Interactive REPL for the cruine command tree."""

from __future__ import annotations

import contextlib
import os
import shlex
import sys
from pathlib import Path

try:
    import readline
except ImportError:  # pragma: no cover - non-POSIX fallback
    readline = None  # type: ignore

from cruine.commands import (
    COMMON_FLAGS,
    RESOLVER,
    TREE,
    Command,
    _find_by_path,
    _full_path,
    _print_node,
    _print_tree,
    dispatch,
)

BUILTINS = ("exit", "quit", "cd", "pwd", "ls", "tree", "help", "clear")


class Repl:
    """Stateful shell that resolves commands relative to the current tree path."""

    def __init__(self, start_path: str | None = None, no_color: bool = False) -> None:
        self.path: list[str] = []
        self.no_color = no_color
        self._exit = False
        self._hist = Path.home() / ".cru_history"
        if start_path:
            tokens = [tok for tok in start_path.split("/") if tok]
            node = self._resolve(tokens)
            if node is None:
                print(f"cru: unknown start path: {start_path}", file=sys.stderr)
            else:
                self.path = _full_path(node)

    def _node(self) -> Command:
        if not self.path:
            return TREE
        node = _find_by_path(self.path)
        return node if node is not None else TREE

    def _resolve(self, tokens: list[str]) -> Command | None:
        node: Command = self._node()
        for token in tokens:
            if token in ("~", "/"):
                node = TREE
            elif token == ".":
                continue
            elif token == "..":
                node = node.parent if node is not TREE and node.parent is not None else TREE
            else:
                child = RESOLVER._lookup[id(node)].get(token)
                if child is None:
                    return None
                node = child
        return node

    def _prompt(self) -> str:
        suffix = "/".join(self.path)
        label = f"cru/{suffix}> " if suffix else "cru> "
        if not self.no_color and sys.stdout.isatty():
            return f"\x1b[1;32m{label}\x1b[0m"
        return label

    def run(self) -> int:
        self._setup_readline()
        print("Cruine shell (crush) - 'help' for guidance, 'exit' to leave")
        while not self._exit:
            try:
                line = input(self._prompt())
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                continue
            line = line.strip()
            if not line:
                continue
            if self._builtin(line):
                continue
            try:
                tokens = shlex.split(line)
            except ValueError as exc:
                print(f"cru: {exc}")
                continue
            if tokens:
                dispatch(self.path + tokens)
        self._save_history()
        return 0

    def _builtin(self, line: str) -> bool:
        parts = line.split(maxsplit=1)
        cmd = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        if cmd in ("exit", "quit"):
            self._exit = True
            return True
        if cmd == "pwd":
            print("cru/" + "/".join(self.path))
            return True
        if cmd == "clear":
            os.system("clear")
            return True
        if cmd == "cd":
            self._cmd_cd(self._path_tokens(rest))
            return True
        if cmd == "ls":
            self._cmd_ls()
            return True
        if cmd == "tree":
            self._cmd_tree(self._path_tokens(rest))
            return True
        if cmd == "help":
            self._cmd_help(self._path_tokens(rest))
            return True
        return False

    @staticmethod
    def _path_tokens(rest: str) -> list[str]:
        tokens: list[str] = []
        for token in shlex.split(rest) if rest else []:
            tokens.extend(part for part in token.split("/") if part)
        return tokens

    def _cmd_cd(self, tokens: list[str]) -> None:
        if not tokens:
            self.path = []
            return
        node = self._resolve(tokens)
        if node is None:
            print(f"cru: unknown path: {' '.join(tokens)}", file=sys.stderr)
            return
        if not node.children:
            print(f"cru: '{' '.join(tokens)}' has no subcommands", file=sys.stderr)
            return
        self.path = _full_path(node)

    def _cmd_ls(self) -> None:
        node = self._node()
        if not node.children:
            print("(no subcommands)")
            return
        for child in node.children:
            preview = ", ".join(child.aliases[:3]) or "-"
            print(f"{child.name:<12} ({preview}) {child.help}")

    def _cmd_tree(self, tokens: list[str]) -> None:
        node = self._resolve(tokens) if tokens else self._node()
        if node is None:
            print(f"cru: unknown path: {' '.join(tokens)}", file=sys.stderr)
            return
        _print_tree(node, 0, 3)

    def _cmd_help(self, tokens: list[str]) -> None:
        if not tokens:
            _print_node(self._node(), self.path)
            print("built-ins : " + ", ".join(BUILTINS))
            print("hint      : tab completes; '..' walks up; 'exit' leaves")
            return
        node = self._resolve(tokens)
        if node is None:
            print(f"cru: unknown path: {' '.join(tokens)}", file=sys.stderr)
            return
        _print_node(node, self.path + tokens)

    def _setup_readline(self) -> None:
        if readline is None or not sys.stdin.isatty():
            return
        with contextlib.suppress(OSError, ValueError):
            readline.read_history_file(self._hist)
        readline.set_completer(self._completer())
        readline.parse_and_bind("tab: complete")

    def _save_history(self) -> None:
        if readline is None or not sys.stdin.isatty():
            return
        with contextlib.suppress(OSError):
            readline.write_history_file(self._hist)

    def _completer(self):
        def completer(text: str, state: int) -> str | None:
            candidates = self._candidates(readline.get_line_buffer())
            matches = [cand for cand in candidates if cand.startswith(text)]
            return matches[state] if state < len(matches) else None

        return completer

    def _candidates(self, buffer: str) -> list[str]:
        trailing = buffer.endswith((" ", "\t"))
        try:
            tokens = shlex.split(buffer)
        except ValueError:
            tokens = buffer.split()
        node = self._resolve(tokens if trailing else tokens[:-1])
        if node is None:
            return []
        candidates = set(BUILTINS)
        for child in node.children:
            candidates.add(child.name)
            candidates.update(child.aliases)
        if not trailing and tokens and tokens[-1].startswith("-"):
            for flag in (*COMMON_FLAGS, *node.flags):
                if flag.short:
                    candidates.add(flag.short)
                if flag.long:
                    candidates.add(flag.long)
        return sorted(candidates)
