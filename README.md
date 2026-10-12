# mcp-minimal

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server in
**one Python file**, with **no dependencies** beyond the standard library.

Copy `mcp_minimal.py` into your project, write a Python function, register it
as a tool, and Claude (Desktop or Code) can call it.

## Why

The official [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
is complete and well maintained. It also has dependencies and a lot of code,
so it is hard to see how the protocol actually works.

`mcp_minimal.py` covers the part most small projects need: tools, progress and
cancellation. It does so in about 400 commented lines that you can read in one
sitting. Use it to:

- **learn MCP**: every message the server reads or writes is visible in the code;
- **give tools to Claude** in a small project, with nothing to install.

## Quick start

```python
from mcp_minimal import Server
server = Server("demo")
@server.tool()
def add(a: int, b: int) -> int: return a + b
server.run()
```

Save it as `demo.py` next to `mcp_minimal.py`, then connect it to Claude as
shown below. Python 3.9 or newer is required, on Windows, macOS or Linux.

## Writing tools

```python
from typing import Annotated, Literal, Optional
from mcp_minimal import Context, Server, ToolError

server = Server("my-tools", version="1.0.0",
                instructions="Optional hints for the model about these tools.")

@server.tool()
def resize(path: str,
           width: Annotated[int, "Width in pixels"],
           mode: Literal["fit", "fill"] = "fit",
           quality: Optional[int] = None) -> dict:
    """Resize an image."""                 # the docstring is the description
    if width <= 0:
        raise ToolError("width must be positive")   # clean error for the model
    return {"path": path, "width": width}  # dict -> JSON text + structuredContent

@server.tool(name="slow-job", annotations={"readOnlyHint": True})
def slow_job(items: list[str], ctx: Context) -> str:
    for i, item in enumerate(items, 1):
        ctx.check_cancelled()              # raises if the user pressed Stop
        ctx.progress(i, total=len(items), message=f"working on {item}")
        ctx.log(f"processing {item}")      # goes to stderr
    return "done"

if __name__ == "__main__":
    server.run()
```

- **Input schema.** It is built from the type hints:
  - `str`, `int`, `float` and `bool`;
  - `list[...]` and `dict[str, ...]`;
  - `Optional[...]`;
  - `Literal[...]`, which becomes an enum;
  - `Annotated[T, "description"]`, which adds a description.

  Parameters with a default value are optional. You can also pass your own
  schema with `@server.tool(schema={...})`.
- **Context.** A parameter annotated as `Context` is filled in by the server and
  is not part of the schema. It gives you:
  - `ctx.progress(value, total, message)`;
  - `ctx.cancelled` and `ctx.check_cancelled()`;
  - `ctx.log()`;
  - `ctx.request_id`.
- **Return values.** A `str` becomes text. `None` becomes empty content.
  Anything else is sent as JSON text, and a `dict` is also sent as
  `structuredContent`.
- **Errors.** A `ToolError` sends its message to the model. Any other exception
  sends `TypeName: message` and logs the traceback to stderr. Either way the
  result is flagged `isError` and the server keeps running.
- **Threads.** Each call runs in its own thread, so a long tool does not block
  other requests or a cancellation. If your tools share state, protect it with
  a lock.
- **Output.** `print()` inside a tool is safe: it goes to stderr, because stdout
  belongs to the protocol.

## Connect to Claude Code

```sh
claude mcp add demo -- python /full/path/to/demo.py
```

On Windows use the full path to `python.exe`, not `pythonw.exe`, which has no
stdin/stdout. Check the connection with `claude mcp list`.

## Connect to Claude Desktop

Open **Settings → Developer → Edit Config**. This opens
`claude_desktop_config.json`, which lives in:

- macOS: `~/Library/Application Support/Claude/`;
- Windows: `%APPDATA%\Claude\`.

Add your server:

```json
{
  "mcpServers": {
    "demo": {
      "command": "python",
      "args": ["/full/path/to/demo.py"]
    }
  }
}
```

On Windows, write paths with double backslashes, for example
`"C:\\Users\\me\\demo.py"`, or with forward slashes. Restart Claude Desktop.
The server's stderr ends up in Claude Desktop's MCP log files, which is the
first place to look when a server does not start.

## Examples

| File | Shows |
| --- | --- |
| [`examples/hello.py`](examples/hello.py) | the smallest server: one tool |
| [`examples/progress.py`](examples/progress.py) | progress notifications and cancellation |
| [`examples/files.py`](examples/files.py) | read-only file tools limited to one folder, with `ToolError` |

## Protocol support

| | |
| --- | --- |
| Transport | stdio: newline-delimited JSON-RPC 2.0, UTF-8, binary streams |
| Protocol versions | `2026-07-28` (stateless, via `server/discover` and `_meta`) and `2025-11-25`, `2025-06-18`, `2025-03-26`, `2024-11-05` (via `initialize`) |
| Methods | `server/discover`, `initialize`, `ping`, `tools/list`, `tools/call` |
| Notifications | `notifications/progress` (sent), `notifications/cancelled` and `notifications/initialized` (received) |

The server speaks both protocol styles:

- Clients that start with `initialize` get the handshake protocol.
- Clients that put `io.modelcontextprotocol/protocolVersion` in a request's
  `_meta` get stateless answers, with `resultType`, server info and caching
  hints.

Both styles were tested with Claude Code 2.1.296, which uses `2026-07-28`, and
with the official Python SDK client 2.3.0, which uses `initialize`.

## Limits

These are the things this file does **not** do, compared with the official SDK:

- **Server features:** only tools. There are no resources, prompts,
  completions or the `tasks` extension, and no client features (sampling,
  elicitation, roots, `input_required` results).
- **Transport:** stdio only. There is no Streamable HTTP or SSE, and no
  authorization.
- **Arguments:** they are not checked against the JSON Schema. Missing or
  unknown arguments still fail cleanly, because Python raises a `TypeError`,
  but types are not checked.
- **Results:**
  - only text content and `structuredContent`, with no images, audio or
    resource links;
  - no `outputSchema`.
- **Tools:**
  - functions are synchronous; `async def` tools are not supported;
  - the tool list is fixed once `run()` starts, so there is no `listChanged`
    and no pagination.
- **Logging:** only to stderr, never as protocol messages.

## Possible future work

- Resources and prompts.
- Streamable HTTP transport.
- Image content in tool results.
- Optional validation of arguments against the input schema.

## Tests

```sh
python -m unittest discover -s tests -v
```

The tests start each server as a subprocess and talk to it in JSON-RPC, the
same way a client does.

## License

[MIT](LICENSE)
