from __future__ import annotations

from pathlib import Path

from config.types import Config

AGENTS_MD_FILENAME = "AGENTS.md"


def discover_agents_md(cwd: Path) -> str | None:
    """Walk from cwd up to the filesystem root, collecting every AGENTS.md found.

    Returned root-to-leaf (least to most specific) — the AGENTS.md spec (see
    prompts/system.py's _get_agents_md_section) says more-deeply-nested files take
    precedence, so ordering root-first lets the model read them as "general, then
    increasingly specific" the way the spec describes.
    """
    found: list[tuple[Path, str]] = []
    current = cwd.resolve()

    while True:
        candidate = current / AGENTS_MD_FILENAME
        if candidate.is_file():
            try:
                found.append((candidate, candidate.read_text(encoding="utf-8")))
            except OSError:
                pass
        parent = current.parent
        if parent == current:
            break
        current = parent

    if not found:
        return None

    found.reverse()
    sections = [f"## {path}\n\n{content.strip()}" for path, content in found]
    return "\n\n".join(sections)


def build_config(
    cwd: Path | None = None,
    user_instructions: str | None = None,
    memory_dir: Path | None = None,
) -> Config:
    """Build a real, fully-populated Config for an actual CLI run — resolves cwd,
    discovers AGENTS.md files, and carries through explicit user instructions."""
    resolved_cwd = (cwd or Path.cwd()).resolve()
    return Config(
        cwd=resolved_cwd,
        developer_instructions=discover_agents_md(resolved_cwd),
        user_instructions=user_instructions,
        memory_dir=memory_dir,
    )
