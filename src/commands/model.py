"""Command tree data structures."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Command", "Flag", "Resolution"]


@dataclass(frozen=True)
class Flag:
    short: str | None
    long: str | None
    help: str
    action: str = "store"
    default: object = None
    metavar: str | None = None

    @property
    def key(self) -> str:
        if self.long:
            return self.long.lstrip("-")
        return self.short.lstrip("-") if self.short else ""

    @property
    def display(self) -> str:
        if self.short and self.long:
            return f"{self.short}, {self.long}"
        return self.short or self.long or ""


@dataclass
class Command:
    name: str
    help: str
    aliases: tuple[str, ...] = ()
    flags: list[Flag] = field(default_factory=list)
    handler: str | None = None
    children: list[Command] = field(default_factory=list)
    positional: str | None = None
    parent: Command | None = field(default=None, repr=False)

    @property
    def is_group(self) -> bool:
        return bool(self.children) and self.handler is None


@dataclass
class Resolution:
    node: Command | None = None
    path: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    flags: dict[str, object] = field(default_factory=dict)
    values: list[str] = field(default_factory=list)
    error: str | None = None

    def flag(self, name: str, default: object = None) -> object:
        return self.flags.get(name, default)
