"""A server with tools that exercise every feature; the tests talk to it."""

import os
import sys
import time
from typing import Annotated, Literal, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mimimalmcp import Context, Server, ToolError  # noqa: E402

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
               extra: Optional[dict[str, int]] = None):
    """Accept many kinds of arguments."""
    return "ok"


@server.tool(schema={"type": "object", "properties": {"x": {"type": "string"}}})
def manual(**kwargs):
    return kwargs


@server.tool()
def echo(text: str) -> str:
    """Return the text unchanged."""
    return text


@server.tool()
def info(ctx: Context) -> dict:
    """Return structured data about the call."""
    ctx.log("info called")
    return {"request_id": ctx.request_id, "tool": ctx.tool_name, "nested": [1, "è"]}


@server.tool()
def crash():
    """Raise an unexpected exception."""
    raise RuntimeError("boom")


@server.tool()
def refuse():
    """Raise a ToolError."""
    raise ToolError("Not allowed here.")


@server.tool()
def chatty() -> str:
    """Print to stdout, which must not reach the protocol stream."""
    print("this goes to stderr")
    return "done"


@server.tool()
def sleep(seconds: float) -> str:
    """Wait, then answer."""
    time.sleep(seconds)
    return f"slept {seconds}"


@server.tool()
def count(steps: int, delay: float, ctx: Context) -> str:
    """Count with progress; stops early when cancelled."""
    for i in range(steps):
        ctx.check_cancelled()
        ctx.progress(i + 1, total=steps, message=f"step {i + 1}")
        ctx.progress(i + 1)                 # repeated value: silently dropped
        time.sleep(delay)
    return f"counted {steps}"


if __name__ == "__main__":
    server.run()
