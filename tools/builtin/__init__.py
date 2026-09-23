from __future__ import annotations

from config.types import Config
from tools.builtin.compact_context import CompactContextTool, GetContextManager, SummarizeFn
from tools.builtin.edit_file import EditFileTool
from tools.builtin.memory import (
    DeleteMemoryTool,
    ListMemoriesTool,
    RecallMemoryTool,
    RememberTool,
    UpdateMemoryTool,
)
from tools.builtin.list_directory import ListDirectoryTool
from tools.builtin.read_file import ReadFileTool
from tools.builtin.search import SearchTool
from tools.builtin.shell import ShellTool
from tools.builtin.tasks import TasksTool
from tools.builtin.web import WebFetchTool, WebSearchTool
from tools.builtin.write_file import WriteFileTool
from tools.registry import ToolRegistry

# Register every new zero-dependency builtin tool here — nothing else needs to know about it.
ZERO_DEP_TOOLS = (
    ReadFileTool,
    EditFileTool,
    WriteFileTool,
    ShellTool,
    ListDirectoryTool,
    SearchTool,
    TasksTool,
    WebFetchTool,
    WebSearchTool,
)


def create_default_registry(
    config: Config | None = None,
    get_context_manager: GetContextManager | None = None,
    summarize: SummarizeFn | None = None,
    registry: ToolRegistry | None = None,
) -> ToolRegistry:
    """The zero-dependency tools, plus the memory tools if `config` is given, plus
    compact_context if `get_context_manager`/`summarize` are given. Fills in only what's
    missing if a registry is already provided, so a caller-supplied registry's own choices
    are never overwritten."""
    registry = registry if registry is not None else ToolRegistry()

    for tool_cls in ZERO_DEP_TOOLS:
        if not registry.has(tool_cls.name):
            registry.register(tool_cls())

    if config is not None:
        if not registry.has(RememberTool.name):
            registry.register(RememberTool(config))
        if not registry.has(RecallMemoryTool.name):
            registry.register(RecallMemoryTool(config))
        if not registry.has(ListMemoriesTool.name):
            registry.register(ListMemoriesTool(config))
        if not registry.has(DeleteMemoryTool.name):
            registry.register(DeleteMemoryTool(config))
        if not registry.has(UpdateMemoryTool.name):
            registry.register(UpdateMemoryTool(config))

    if get_context_manager is not None and summarize is not None:
        if not registry.has(CompactContextTool.name):
            registry.register(CompactContextTool(get_context_manager, summarize))

    return registry
