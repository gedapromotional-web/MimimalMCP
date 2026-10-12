"""The smallest useful MCP server: one tool that greets someone.

Try it:  claude mcp add hello -- python /full/path/to/examples/hello.py
"""

import os
import sys

# Only needed because this example lives in a subfolder of mcp_minimal.py.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_minimal import Server  # noqa: E402

server = Server("hello")


@server.tool()
def greet(name: str, excited: bool = False) -> str:
    """Greet someone by name."""
    return f"Hello, {name}{'!' if excited else '.'}"


if __name__ == "__main__":
    server.run()
