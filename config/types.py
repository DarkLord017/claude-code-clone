from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    cwd: Path = field(default_factory=Path.cwd)
    developer_instructions: str | None = None
    user_instructions: str | None = None
    memory_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.memory_dir is None:
            self.memory_dir = self.cwd / ".agent" / "memory"
