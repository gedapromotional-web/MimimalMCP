"""Read-only file tools, limited to one folder.

Usage:  python examples/files.py /path/to/folder   (default: current folder)

The tools refuse any path outside that folder, including "../" tricks and
symbolic links that point elsewhere.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_minimal import Server, ToolError  # noqa: E402

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
READ_ONLY = {"readOnlyHint": True}

server = Server("files", instructions=f"Paths are relative to {ROOT}.")


def inside_root(relative: str) -> Path:
    """Resolve a user-given path and make sure it stays inside ROOT."""
    path = (ROOT / relative).resolve()
    if path != ROOT and ROOT not in path.parents:
        raise ToolError(f"{relative!r} is outside the allowed folder.")
    return path


@server.tool(annotations=READ_ONLY)
def list_files(folder: str = ".", pattern: str = "*") -> dict:
    """List files and folders in a folder (relative path), with sizes in bytes."""
    path = inside_root(folder)
    if not path.is_dir():
        raise ToolError(f"{folder!r} is not a folder.")
    entries = []
    for item in sorted(path.glob(pattern)):
        if item.is_dir():
            entries.append({"name": item.name + "/", "size": None})
        else:
            entries.append({"name": item.name, "size": item.stat().st_size})
    return {"folder": str(path.relative_to(ROOT)), "entries": entries}


@server.tool(annotations=READ_ONLY)
def read_file(path: str, max_chars: int = 20000) -> str:
    """Read a UTF-8 text file (relative path). Long files are cut at max_chars."""
    target = inside_root(path)
    if not target.is_file():
        raise ToolError(f"{path!r} is not a file.")
    text = target.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n... [cut: {len(text) - max_chars} more characters]"
    return text


if __name__ == "__main__":
    server.run()
