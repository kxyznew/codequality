"""Shared models for scanner results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Diagnostic:
    tool: str
    rule_id: str
    message: str
    level: str
    path: str | None = None
    line: int | None = None
    column: int | None = None
    end_line: int | None = None
    end_column: int | None = None

    @property
    def sarif_rule_id(self) -> str:
        prefix = "".join(character if character.isalnum() else "-" for character in self.tool.lower())
        return f"{prefix}-{self.rule_id}"


@dataclass
class ScanReport:
    diagnostics: list[Diagnostic] = field(default_factory=list)
    scanners_run: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
