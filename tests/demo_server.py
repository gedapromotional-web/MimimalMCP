"""A server with tools that exercise every feature; the tests talk to it."""

import os
import sys
from typing import Annotated, Literal, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_minimal import Server  # noqa: E402

server = Server("demo", version="1.2.3", instructions="Test server.")


@server.tool()
def add(a: int, b: int = 1) -> int:
    """Add two numbers."""
    return a + b


@server.tool(name="typed", title="Typed arguments", annotations={"readOnlyHint": True})
def typed_tool(text: str, ratio: float, flag: bool, tags: list[str],
               mode: Literal["fast", "slow"] = "fast",
               limit: Optional[int] = None,
               note: Annotated[str, "A free note."] = "",
               extra: dict[str, int] = None):
    """Accept many kinds of arguments."""
    return "ok"


@server.tool(schema={"type": "object", "properties": {"x": {"type": "string"}}})
def manual(**kwargs):
    return kwargs


if __name__ == "__main__":
    server.run()
