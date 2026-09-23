from __future__ import annotations

from pathlib import Path


def file_not_found(path: Path) -> str:
    return f"File not found: {path}"


def edit_file_not_found(path: Path) -> str:
    return f"File not found: {path}. edit_file only edits existing files — read it first."


def path_not_a_file(path: Path) -> str:
    return f"Path is not a file: {path}"


def file_too_large(size_bytes: int, max_bytes: int) -> str:
    return (
        f"File too large ({size_bytes / (1024 * 1024):.1f}MB). "
        f"Maximum is {max_bytes / (1024 * 1024):.0f}MB."
    )


def cannot_read_binary_file(name: str, size_str: str) -> str:
    return f"Cannot read binary file: {name} ({size_str}) This tool only reads text files."


def cannot_edit_binary_file(name: str) -> str:
    return f"Cannot edit binary file: {name}"


def read_failed(error: Exception) -> str:
    return f"Failed to read file: {error}"


def write_failed(error: Exception) -> str:
    return f"Failed to write file: {error}"


def no_op_edit() -> str:
    return "old_string and new_string are identical — nothing to change."


def old_string_not_found() -> str:
    return (
        "old_string not found in file. It must match the file's exact text, including "
        "whitespace and indentation — re-read the file to get the exact content."
    )


def old_string_ambiguous(occurrences: int, lines: str) -> str:
    return (
        f"old_string is not unique — it appears {occurrences} times in the file, "
        f"at lines {lines}. Add more surrounding context to make it unique, or set replace_all=true."
    )


def unknown_tool(name: str) -> str:
    return f"Unknown tool: '{name}'"


def invalid_params(name: str, params: dict) -> str:
    return f"Invalid parameters for tool '{name}': {params}"


def unhandled_tool_error(name: str, error: Exception) -> str:
    return f"Tool '{name}' raised an unhandled error: {error}"


def already_registered(name: str) -> str:
    return f"Tool '{name}' is already registered."


def not_registered(name: str) -> str:
    return f"Tool '{name}' is not registered."


def mutating_confirmation(tool_name: str) -> str:
    return f"Tool '{tool_name}' is about to perform a mutating operation. Please confirm to proceed."
