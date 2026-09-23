from __future__ import annotations

import re
from pathlib import Path

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "memory"


def entry_path(memory_dir: Path, name: str) -> Path:
    return memory_dir / f"{_slugify(name)}.md"


def index_path(memory_dir: Path) -> Path:
    return memory_dir / "MEMORY.md"


def write_entry(memory_dir: Path, name: str, description: str, content: str) -> Path:
    memory_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify(name)
    path = entry_path(memory_dir, slug)

    text = f"---\nname: {slug}\ndescription: {description}\n---\n\n{content.strip()}\n"
    path.write_text(text, encoding="utf-8")

    _update_index(memory_dir, slug, description)
    return path


def update_entry(
    memory_dir: Path,
    name: str,
    description: str | None = None,
    content: str | None = None,
) -> bool:
    """Update an EXISTING memory, changing only the fields provided. Returns False if it doesn't exist."""
    slug = _slugify(name)
    parsed = _read_parsed(memory_dir, slug)
    if parsed is None:
        return False

    existing_description, existing_content = parsed
    write_entry(
        memory_dir,
        slug,
        description if description is not None else existing_description,
        content if content is not None else existing_content,
    )
    return True


def delete_entry(memory_dir: Path, name: str) -> bool:
    """Delete one memory's file and its index line. Returns False if it didn't exist."""
    slug = _slugify(name)
    path = entry_path(memory_dir, slug)
    if not path.exists():
        return False

    path.unlink()
    _remove_from_index(memory_dir, slug)
    return True


def _update_index(memory_dir: Path, slug: str, description: str) -> None:
    """Upsert this entry's line in MEMORY.md, keeping one line per slug."""
    idx_path = index_path(memory_dir)
    lines = idx_path.read_text(encoding="utf-8").splitlines() if idx_path.exists() else []
    lines = _without_slug(lines, slug)
    lines.append(f"- [{slug}]({slug}.md) — {description}")

    idx_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _remove_from_index(memory_dir: Path, slug: str) -> None:
    idx_path = index_path(memory_dir)
    if not idx_path.exists():
        return

    lines = _without_slug(idx_path.read_text(encoding="utf-8").splitlines(), slug)
    if lines:
        idx_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        idx_path.unlink()  # no memories left — remove the empty index entirely


def _without_slug(lines: list[str], slug: str) -> list[str]:
    prefix = f"- [{slug}]("
    return [line for line in lines if not line.startswith(prefix)]


def read_index(memory_dir: Path) -> str | None:
    """The full index text, or None if no memories have been saved yet."""
    idx_path = index_path(memory_dir)
    if not idx_path.exists():
        return None
    text = idx_path.read_text(encoding="utf-8").strip()
    return text or None


def read_entry(memory_dir: Path, name: str) -> str | None:
    """The body of one memory (frontmatter stripped), or None if it doesn't exist."""
    parsed = _read_parsed(memory_dir, _slugify(name))
    return parsed[1] if parsed else None


def _read_parsed(memory_dir: Path, slug: str) -> tuple[str, str] | None:
    """(description, body) for an existing entry, or None if it doesn't exist."""
    path = entry_path(memory_dir, slug)
    if not path.exists():
        return None

    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return "", text.strip()

    frontmatter, body = match.groups()
    description = ""
    for line in frontmatter.splitlines():
        if line.startswith("description:"):
            description = line.split(":", 1)[1].strip()
    return description, body.strip()
