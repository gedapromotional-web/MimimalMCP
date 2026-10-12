"""mcp_minimal: a Model Context Protocol (MCP) server in one file.

Copy this file into your project, decorate a few functions, call run():

    from mcp_minimal import Server

    server = Server("demo")

    @server.tool()
    def add(a: int, b: int) -> int:
        "Add two numbers."
        return a + b

    server.run()

How it works, in short:

  * The client (Claude Desktop, Claude Code, ...) starts your script as a
    subprocess and speaks JSON-RPC 2.0 over stdin/stdout: one JSON object
    per line. stdout belongs to the protocol; every log line goes to stderr.
  * The client calls `initialize`, then `tools/list` to learn which tools
    exist (name, description, JSON Schema of the arguments).
  * `tools/call` runs one tool and returns its result as content blocks.

Standard library only, Python 3.9+, MIT license.
"""

import inspect
import json
import re
import sys
import threading
import traceback
import types
import typing

__version__ = "0.1.0"
__all__ = ["Server", "Context", "ToolError", "Cancelled"]

# Versions negotiated by `initialize`, newest first.
HANDSHAKE_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

# JSON-RPC error codes.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class ToolError(Exception):
    """Raise inside a tool to send a clean error message (no traceback) to the model."""


class Cancelled(Exception):
    """Raised by Context.check_cancelled() once the client cancelled the call."""


class _RpcError(Exception):
    """A JSON-RPC error answer (protocol problem, not a tool failure)."""

    def __init__(self, code, message, data=None):
        super().__init__(message)
        self.code, self.message, self.data = code, message, data


# ----------------------------------------------------------------------------
# JSON Schema from type hints
# ----------------------------------------------------------------------------

_JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean",
               dict: "object", list: "array", type(None): "null"}


def _schema_for(hint):
    """Turn one Python type hint into a JSON Schema fragment (best effort)."""
    origin, args = typing.get_origin(hint), typing.get_args(hint)
    if origin is typing.Annotated:              # Annotated[int, "description"]
        schema = _schema_for(args[0])
        notes = [a for a in args[1:] if isinstance(a, str)]
        if notes:
            schema["description"] = " ".join(notes)
        return schema
    if origin is typing.Union or origin is getattr(types, "UnionType", None):
        options = [_schema_for(a) for a in args]  # Optional[int], int | None
        return options[0] if len(options) == 1 else {"anyOf": options}
    if origin is typing.Literal:                # Literal["a", "b"] -> enum
        return {"enum": list(args)}
    if origin is list and args:                 # list[str]
        return {"type": "array", "items": _schema_for(args[0])}
    if origin is dict and len(args) == 2:       # dict[str, int]
        return {"type": "object", "additionalProperties": _schema_for(args[1])}
    if origin in (list, dict):
        hint = origin
    if hint in _JSON_TYPES:
        return {"type": _JSON_TYPES[hint]}
    return {}                                   # Any or unknown: accept anything


def _inspect_tool(func):
    """Build the input schema of `func`. Returns (schema, context parameter)."""
    hints = typing.get_type_hints(func, include_extras=True)
    properties, required, ctx_param = {}, [], None
    for name, param in inspect.signature(func).parameters.items():
        hint = hints.get(name, typing.Any)
        if hint is Context:                     # injected by us, not by the client
            ctx_param = name
            continue
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        prop = _schema_for(hint)
        if param.default is param.empty:
            required.append(name)
        elif isinstance(param.default, (str, int, float, bool, type(None))):
            prop["default"] = param.default
        properties[name] = prop
    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema, ctx_param


# ----------------------------------------------------------------------------
# Tool calls
# ----------------------------------------------------------------------------

class Context:
    """Handed to a tool that has a parameter annotated as `Context`."""

    def __init__(self, server, request_id, tool_name, progress_token=None):
        self.request_id = request_id
        self.tool_name = tool_name
        self._server = server
        self._token = progress_token        # set only if the client wants progress
        self._last = None                   # last progress value sent
        self._finished = False
        self._cancel = threading.Event()

    @property
    def cancelled(self):
        """True once the client sent notifications/cancelled for this call."""
        return self._cancel.is_set()

    def check_cancelled(self):
        """Raise Cancelled if the call was cancelled. Handy inside loops."""
        if self._cancel.is_set():
            raise Cancelled()

    def progress(self, progress, total=None, message=None):
        """Report progress, e.g. ctx.progress(3, 10, "file 3 of 10").

        Does nothing when the client did not ask for progress, after the call
        ended or was cancelled, or when the value does not grow (MCP requires
        each notification to increase).
        """
        if self._token is None or self._finished or self.cancelled:
            return
        if self._last is not None and progress <= self._last:
            return
        self._last = progress
        params = {"progressToken": self._token, "progress": progress}
        if total is not None:
            params["total"] = total
        if message is not None:
            params["message"] = message
        self._server._send({"jsonrpc": "2.0", "method": "notifications/progress", "params": params})

    def log(self, message):
        """Write a line to stderr, tagged with the tool name."""
        self._server.log(f"{self.tool_name}: {message}")


def _to_result(value):
    """Turn what a tool returned into an MCP CallToolResult."""
    if value is None:
        return {"content": []}
    if isinstance(value, str):
        return {"content": [{"type": "text", "text": value}]}
    text = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    result = {"content": [{"type": "text", "text": text}]}
    if isinstance(value, dict):             # objects also go as structured data
        result["structuredContent"] = json.loads(text)
    return result


def _error_result(message):
    """A failed tool call: still a normal result, flagged with isError."""
    return {"content": [{"type": "text", "text": message}], "isError": True}


# ----------------------------------------------------------------------------
# The server
# ----------------------------------------------------------------------------

_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class Server:
    """An MCP server that speaks over stdin/stdout."""

    def __init__(self, name, version="0.1.0", instructions=None):
        self.name, self.version, self.instructions = name, version, instructions
        self._tools = {}            # name -> (function, tool description, ctx param)
        self._out = None            # binary stdout, set by run()
        self._active = {}           # request id -> Context of a running tool
        self._lock = threading.Lock()   # guards stdout and _active

    # -- registration --------------------------------------------------------

    def tool(self, func=None, *, name=None, title=None, description=None,
             schema=None, annotations=None):
        """Register a function as a tool. Use as @server.tool or @server.tool(...).

        name         defaults to the function name
        description  defaults to the docstring
        schema       JSON Schema of the arguments; built from type hints if omitted
        annotations  optional hints for the client, e.g. {"readOnlyHint": True}
        """
        def register(f):
            tool_name = name or f.__name__
            if not _TOOL_NAME.match(tool_name):
                raise ValueError(f"invalid tool name {tool_name!r}: use 1-128 of A-Z a-z 0-9 _ . -")
            auto_schema, ctx_param = _inspect_tool(f)
            spec = {"name": tool_name,
                    "description": description or inspect.getdoc(f) or "",
                    "inputSchema": schema or auto_schema}
            if title:
                spec["title"] = title
            if annotations:
                spec["annotations"] = annotations
            self._tools[tool_name] = (f, spec, ctx_param)
            return f
        return register(func) if func is not None else register

    # -- input / output ------------------------------------------------------

    def log(self, message):
        """Write a line to stderr (Claude Desktop shows it in its MCP log)."""
        print(f"[{self.name}] {message}", file=sys.stderr, flush=True)

    def _send(self, message):
        # json.dumps escapes newlines inside strings, so one message = one line.
        data = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        with self._lock:            # tool threads write too
            self._out.write(data.encode("utf-8", "replace") + b"\n")
            self._out.flush()

    def _send_error(self, msg_id, code, message, data=None):
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        self._send({"jsonrpc": "2.0", "id": msg_id, "error": error})

    def run(self):
        """Serve requests on stdin/stdout until stdin is closed."""
        # Binary streams: no newline translation on Windows, and we choose UTF-8
        # ourselves instead of the console code page.
        self._out = sys.stdout.buffer
        sys.stdout = sys.stderr     # a stray print() in a tool must not corrupt stdout
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
        self.log(f"{self.name} {self.version} ready with {len(self._tools)} tool(s)")
        stdin = sys.stdin.buffer
        while True:
            line = stdin.readline()
            if not line:            # EOF: the client is gone, so are we
                break
            if line.strip():
                self._handle_line(line)
        self.log("stdin closed, bye")

    # -- dispatch ------------------------------------------------------------

    def _handle_line(self, line):
        try:
            message = json.loads(line)  # bytes in, UTF-8 detected by json
        except ValueError:
            return self._send_error(None, PARSE_ERROR, "Parse error")
        if not isinstance(message, dict):   # batches were removed in 2025-06-18
            return self._send_error(None, INVALID_REQUEST, "Expected one JSON object per line")
        method, msg_id = message.get("method"), message.get("id")
        if not isinstance(method, str):
            return                          # a response: we never ask, so ignore it
        params = message.get("params") or {}
        try:
            if not isinstance(params, dict):
                raise _RpcError(INVALID_PARAMS, "params must be an object")
            if "id" not in message:
                return self._notification(method, params)
            result = self._request(msg_id, method, params)
        except _RpcError as e:
            return self._send_error(msg_id, e.code, e.message, e.data)
        except Exception as e:              # a bug here must not kill the server
            self.log(traceback.format_exc())
            return self._send_error(msg_id, INTERNAL_ERROR, f"Internal error: {e}")
        if result is not None:              # None: a tool thread answers later
            self._send({"jsonrpc": "2.0", "id": msg_id, "result": result})

    def _notification(self, method, params):
        # notifications/initialized and unknown notifications need nothing.
        if method == "notifications/cancelled":
            request_id = params.get("requestId")
            if isinstance(request_id, (str, int)):
                with self._lock:
                    ctx = self._active.get(request_id)
                if ctx is not None:
                    ctx._cancel.set()       # the tool sees ctx.cancelled == True
                    ctx.log(f"cancelled ({params.get('reason') or 'no reason given'})")

    def _request(self, msg_id, method, params):
        if method == "initialize":
            wanted = params.get("protocolVersion")
            result = {"protocolVersion": wanted if wanted in HANDSHAKE_VERSIONS else HANDSHAKE_VERSIONS[0],
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": self.name, "version": self.version}}
            if self.instructions:
                result["instructions"] = self.instructions
            return result
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [spec for _, spec, _ in self._tools.values()]}
        if method == "tools/call":
            return self._start_call(msg_id, params)
        raise _RpcError(METHOD_NOT_FOUND, f"Method not found: {method}")

    # -- tool calls ----------------------------------------------------------

    def _start_call(self, msg_id, params):
        """Start a tool in its own thread, so we keep reading stdin meanwhile."""
        name, args = params.get("name"), params.get("arguments") or {}
        if not isinstance(name, str) or name not in self._tools:
            raise _RpcError(INVALID_PARAMS, f"Unknown tool: {name}")
        if not isinstance(args, dict):
            raise _RpcError(INVALID_PARAMS, "arguments must be an object")
        func, _, ctx_param = self._tools[name]
        meta = params.get("_meta") or {}
        ctx = Context(self, msg_id, name, meta.get("progressToken"))
        if ctx_param:
            args = {**args, ctx_param: ctx}
        with self._lock:
            self._active[msg_id] = ctx
        threading.Thread(target=self._run_tool, args=(func, args, ctx),
                         name=f"tool-{name}", daemon=True).start()
        return None                         # the thread sends the answer

    def _run_tool(self, func, args, ctx):
        try:
            result = _to_result(func(**args))
        except Cancelled:
            result = None
        except ToolError as e:              # expected failure: just the message
            result = _error_result(str(e))
        except Exception as e:              # bug or bad arguments: report, keep serving
            ctx.log(f"failed\n{traceback.format_exc()}")
            result = _error_result(f"{type(e).__name__}: {e}")
        ctx._finished = True
        with self._lock:
            self._active.pop(ctx.request_id, None)
        if not ctx.cancelled:               # a cancelled call gets no answer at all
            self._send({"jsonrpc": "2.0", "id": ctx.request_id, "result": result})
