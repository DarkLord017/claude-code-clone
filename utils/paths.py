from __future__ import annotations

from pathlib import Path

TEXT_BYTES = bytes(range(0x20, 0x100)) + b"\n\r\t\f\b"


def resolve_path(base: str | Path, path: str | Path) -> Path:
    path = Path(path)
    if path.is_absolute():
        return path.resolve()

    return (Path(base) / path).resolve()


def is_binary_file(path: str | Path, sample_size: int = 8192) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(sample_size)
    except OSError:
        return False

    if not chunk:
        return False

    if b"\x00" in chunk:
        return True

    non_text = chunk.translate(None, TEXT_BYTES)
    return len(non_text) / len(chunk) > 0.30
