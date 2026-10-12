"""End-to-end tests: start a server as a subprocess and speak JSON-RPC to it.

Run with:  python -m unittest discover -s tests -v
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(HERE, "demo_server.py")
EXAMPLES = os.path.join(os.path.dirname(HERE), "examples")


class Client:
    """A tiny MCP client: writes requests to stdin, reads lines from stdout."""

    def __init__(self, script=DEMO, *args):
        self.proc = subprocess.Popen([sys.executable, script, *args], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.lines, self.stderr, self.next_id = queue.Queue(), [], 0
        threading.Thread(target=self._pump, args=(self.proc.stdout, self.lines.put), daemon=True).start()
        threading.Thread(target=self._pump, args=(self.proc.stderr, self.stderr.append), daemon=True).start()

    @staticmethod
    def _pump(stream, sink):
        for line in iter(stream.readline, b""):
            sink(line)

    def send_raw(self, data):
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def send(self, message):
        self.send_raw(json.dumps(message).encode("utf-8") + b"\n")

    def recv(self, timeout=5):
        line = self.lines.get(timeout=timeout)
        assert line.endswith(b"\n") and not line.endswith(b"\r\n"), line
        return json.loads(line.decode("utf-8"))   # stdout must hold only JSON

    def request(self, method, params=None, timeout=5):
        """Send a request, return (response, notifications received meanwhile)."""
        self.next_id += 1
        message = {"jsonrpc": "2.0", "id": self.next_id, "method": method}
        if params is not None:
            message["params"] = params
        self.send(message)
        notes = []
        while True:
            reply = self.recv(timeout)
            if reply.get("id") == self.next_id and "method" not in reply:
                return reply, notes
            notes.append(reply)

    def close(self):
        if self.proc.stdin and not self.proc.stdin.closed:
            self.proc.stdin.close()
        try:
            return self.proc.wait(timeout=5)
        finally:
            self.proc.stdout.close()
            self.proc.stderr.close()


class ServerTest(unittest.TestCase):

    def setUp(self):
        self.client = Client()

    def tearDown(self):
        self.client.close()

    def call(self, method, params=None):
        return self.client.request(method, params)[0]

    def test_initialize_echoes_known_version(self):
        result = self.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                          "clientInfo": {"name": "t", "version": "0"}})["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertEqual(result["serverInfo"], {"name": "demo", "version": "1.2.3"})
        self.assertEqual(result["instructions"], "Test server.")
        self.assertIn("tools", result["capabilities"])

    def test_initialize_unknown_version_gets_latest(self):
        result = self.call("initialize", {"protocolVersion": "1999-01-01"})["result"]
        self.assertEqual(result["protocolVersion"], "2025-11-25")

    def test_ping_and_initialized_notification(self):
        self.client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(self.call("ping")["result"], {})

    def test_tools_list_schema_from_hints(self):
        tools = {t["name"]: t for t in self.call("tools/list")["result"]["tools"]}
        self.assertEqual(list(tools)[:3], ["add", "typed", "manual"])
        self.assertNotIn("ctx", tools["info"]["inputSchema"]["properties"])
        add = tools["add"]
        self.assertEqual(add["description"], "Add two numbers.")
        self.assertEqual(add["inputSchema"], {
            "type": "object", "required": ["a"],
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer", "default": 1}}})
        typed = tools["typed"]
        self.assertEqual(typed["title"], "Typed arguments")
        self.assertEqual(typed["annotations"], {"readOnlyHint": True})
        props = typed["inputSchema"]["properties"]
        self.assertEqual(typed["inputSchema"]["required"], ["text", "ratio", "flag", "tags"])
        self.assertEqual(props["ratio"], {"type": "number"})
        self.assertEqual(props["flag"], {"type": "boolean"})
        self.assertEqual(props["tags"], {"type": "array", "items": {"type": "string"}})
        self.assertEqual(props["mode"], {"enum": ["fast", "slow"], "default": "fast"})
        self.assertEqual(props["limit"], {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": None})
        self.assertEqual(props["note"], {"type": "string", "description": "A free note.", "default": ""})
        self.assertEqual(props["extra"]["anyOf"][0]["additionalProperties"], {"type": "integer"})
        self.assertEqual(tools["manual"]["inputSchema"]["properties"], {"x": {"type": "string"}})

    def test_protocol_errors(self):
        self.assertEqual(self.call("nope")["error"]["code"], -32601)
        self.assertEqual(self.call("ping", [1, 2])["error"]["code"], -32602)
        self.client.send_raw(b"{not json\n")
        self.assertEqual(self.client.recv()["error"]["code"], -32700)
        self.client.send_raw(b'[{"jsonrpc":"2.0","id":1,"method":"ping"}]\n')
        self.assertEqual(self.client.recv()["error"]["code"], -32600)
        self.assertEqual(self.call("ping")["result"], {})      # still alive

    def tool(self, name, arguments=None):
        return self.call("tools/call", {"name": name, "arguments": arguments or {}})

    def test_call_returns_text(self):
        self.assertEqual(self.tool("add", {"a": 2, "b": 3})["result"],
                         {"content": [{"type": "text", "text": "5"}]})

    def test_call_unicode_round_trip(self):
        text = "caffè ☕ 日本 \U0001F600 line1\nline2"
        self.assertEqual(self.tool("echo", {"text": text})["result"]["content"][0]["text"], text)

    def test_call_dict_gives_structured_content(self):
        result = self.tool("info")["result"]
        self.assertEqual(result["structuredContent"]["tool"], "info")
        self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])

    def test_tool_exception_is_error_result(self):
        result = self.tool("crash")["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(result["content"][0]["text"], "RuntimeError: boom")
        self.assertEqual(self.tool("add", {"a": 1})["result"]["content"][0]["text"], "2")

    def test_tool_error_message(self):
        result = self.tool("refuse")["result"]
        self.assertEqual(result, {"content": [{"type": "text", "text": "Not allowed here."}], "isError": True})

    def test_bad_arguments_are_tool_errors(self):
        self.assertTrue(self.tool("add", {})["result"]["isError"])
        self.assertTrue(self.tool("add", {"a": 1, "zzz": 2})["result"]["isError"])

    def test_unknown_tool_is_protocol_error(self):
        self.assertEqual(self.tool("missing")["error"]["code"], -32602)
        self.assertEqual(self.call("tools/call", {"name": "add", "arguments": [1]})["error"]["code"], -32602)

    def test_print_in_tool_goes_to_stderr(self):
        self.assertEqual(self.tool("chatty")["result"]["content"][0]["text"], "done")
        self.client.close()
        self.assertIn(b"this goes to stderr\n", b"".join(self.client.stderr))

    def test_slow_tool_does_not_block_other_requests(self):
        self.client.send({"jsonrpc": "2.0", "id": "slow", "method": "tools/call",
                          "params": {"name": "sleep", "arguments": {"seconds": 1}}})
        self.assertEqual(self.call("ping")["result"], {})     # answered first
        self.assertEqual(self.client.recv()["id"], "slow")

    def test_progress_notifications(self):
        reply, notes = self.client.request("tools/call", {
            "name": "count", "arguments": {"steps": 3, "delay": 0}, "_meta": {"progressToken": "tok"}})
        self.assertEqual(reply["result"]["content"][0]["text"], "counted 3")
        self.assertEqual([n["method"] for n in notes], ["notifications/progress"] * 3)
        self.assertEqual(notes[0]["params"], {"progressToken": "tok", "progress": 1, "total": 3,
                                              "message": "step 1"})
        self.assertEqual([n["params"]["progress"] for n in notes], [1, 2, 3])

    def test_no_progress_without_token(self):
        reply, notes = self.client.request("tools/call", {"name": "count", "arguments": {"steps": 2, "delay": 0}})
        self.assertEqual(notes, [])

    def test_cancel_stops_tool_and_suppresses_answer(self):
        self.client.send({"jsonrpc": "2.0", "id": 99, "method": "tools/call", "params": {
            "name": "count", "arguments": {"steps": 50, "delay": 0.05}, "_meta": {"progressToken": 7}}})
        self.assertEqual(self.client.recv()["method"], "notifications/progress")
        self.client.send({"jsonrpc": "2.0", "method": "notifications/cancelled",
                          "params": {"requestId": 99, "reason": "user stop"}})
        reply, notes = self.client.request("ping")
        self.assertEqual(reply["result"], {})
        time.sleep(0.3)                     # longer than one step of the tool
        late = []
        while not self.client.lines.empty():
            late.append(self.client.recv())
        seen = notes + late
        self.assertFalse([m for m in seen if m.get("id") == 99], seen)
        self.assertLess(len(seen), 5)       # progress stopped quickly
        self.client.close()
        self.assertIn(b"cancelled (user stop)", b"".join(self.client.stderr))

    def test_cancel_unknown_request_is_ignored(self):
        self.client.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 12345}})
        self.client.send({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": [1]}})
        self.assertEqual(self.call("ping")["result"], {})

    # -- stateless protocol (2026-07-28) --

    META = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {}}
    SERVER_INFO = {"io.modelcontextprotocol/serverInfo": {"name": "demo", "version": "1.2.3"}}

    def test_discover(self):
        result = self.call("server/discover", {"_meta": self.META})["result"]
        self.assertEqual(result, {"supportedVersions": ["2026-07-28"], "capabilities": {"tools": {}},
                                  "instructions": "Test server.", "ttlMs": 0, "cacheScope": "public",
                                  "resultType": "complete", "_meta": self.SERVER_INFO})
        self.assertEqual(self.call("server/discover")["result"]["supportedVersions"], ["2026-07-28"])

    def test_stateless_tools_without_initialize(self):
        result = self.call("tools/list", {"_meta": self.META})["result"]
        self.assertEqual((result["resultType"], result["ttlMs"], result["cacheScope"]), ("complete", 0, "public"))
        self.assertEqual(result["_meta"], self.SERVER_INFO)
        reply, notes = self.client.request("tools/call", {
            "name": "count", "arguments": {"steps": 2, "delay": 0},
            "_meta": dict(self.META, progressToken="p")})
        self.assertEqual(reply["result"]["resultType"], "complete")
        self.assertEqual(reply["result"]["content"][0]["text"], "counted 2")
        self.assertEqual(len(notes), 2)

    def test_handshake_results_have_no_stateless_fields(self):
        self.assertNotIn("resultType", self.call("tools/list")["result"])
        self.assertNotIn("resultType", self.tool("add", {"a": 1})["result"])

    def test_stateless_version_errors(self):
        error = self.call("tools/list", {"_meta": dict(self.META, **{
            "io.modelcontextprotocol/protocolVersion": "1900-01-01"})})["error"]
        self.assertEqual(error["code"], -32022)
        self.assertEqual(error["data"], {"supported": ["2026-07-28"], "requested": "1900-01-01"})
        error = self.call("tools/list", {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}})["error"]
        self.assertEqual(error["code"], -32602)

    def test_exits_when_stdin_closes(self):
        self.assertEqual(self.client.close(), 0)



class ExamplesTest(unittest.TestCase):
    """Each example starts, lists its tools and answers one call."""

    def run_example(self, script, *args):
        client = Client(os.path.join(EXAMPLES, script), *args)
        self.addCleanup(client.close)
        client.request("initialize", {"protocolVersion": "2025-11-25"})
        names = [t["name"] for t in client.request("tools/list")[0]["result"]["tools"]]
        return client, names

    def call(self, client, name, arguments, meta=None):
        params = {"name": name, "arguments": arguments}
        if meta:
            params["_meta"] = meta
        return client.request("tools/call", params)

    def test_hello(self):
        client, names = self.run_example("hello.py")
        self.assertEqual(names, ["greet"])
        reply, _ = self.call(client, "greet", {"name": "Ada", "excited": True})
        self.assertEqual(reply["result"]["content"][0]["text"], "Hello, Ada!")

    def test_progress(self):
        client, names = self.run_example("progress.py")
        self.assertEqual(names, ["slow_count"])
        reply, notes = self.call(client, "slow_count", {"to": 3, "seconds_per_step": 0}, {"progressToken": 1})
        self.assertEqual(reply["result"]["content"][0]["text"], "Counted to 3.")
        self.assertEqual(len(notes), 3)

    def test_files(self):
        client, names = self.run_example("files.py", HERE)
        self.assertEqual(names, ["list_files", "read_file"])
        reply, _ = self.call(client, "list_files", {"pattern": "*.py"})
        found = [e["name"] for e in reply["result"]["structuredContent"]["entries"]]
        self.assertIn("test_server.py", found)
        reply, _ = self.call(client, "read_file", {"path": "demo_server.py", "max_chars": 10})
        self.assertTrue(reply["result"]["content"][0]["text"].startswith('"""A serve\n... [cut:'))
        reply, _ = self.call(client, "read_file", {"path": "../LICENSE"})
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("outside the allowed folder", reply["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
