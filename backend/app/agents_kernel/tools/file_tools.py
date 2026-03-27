"""Virtual file helpers backed by graph state."""

from __future__ import annotations

from app.agents_kernel.state import SentinelAgentState
from app.agents_kernel.trace import record_tool_call


def write_virtual_file(state: SentinelAgentState, filename: str, content: str) -> str:
    """Write a virtual file into graph state."""

    files = dict(state.get("files", {}))
    files[filename] = content
    state["files"] = files
    record_tool_call(
        state,
        "write_virtual_file",
        arguments_summary=filename,
        result_summary=f"{filename} stored ({len(content)} chars)",
    )
    return content


def read_virtual_file(state: SentinelAgentState, filename: str) -> str | None:
    """Read a virtual file from graph state."""

    content = (state.get("files") or {}).get(filename)
    result_summary = f"{filename} returned" if content is not None else f"{filename} missing"
    record_tool_call(
        state,
        "read_virtual_file",
        arguments_summary=filename,
        result_summary=result_summary,
    )
    return content


def list_virtual_files(state: SentinelAgentState) -> list[dict[str, int | str]]:
    """List virtual files with sizes."""

    files = state.get("files") or {}
    listing = [{"filename": name, "size": len(content)} for name, content in sorted(files.items())]
    record_tool_call(
        state,
        "list_virtual_files",
        arguments_summary="list files",
        result_summary=f"{len(listing)} files returned",
    )
    return listing
