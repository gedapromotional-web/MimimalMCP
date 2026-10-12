"""End-to-end tests: start a server as a subprocess and speak JSON-RPC to it.

Run with:  python -m unittest discover -s tests -v
"""

import json
import os
import queue
import subprocess
import sys
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.join(HERE, "demo_server.py")


class Client:
    """A tiny MCP client: writes requests to stdin, reads lines from stdout."""

    def __init__(self, script=DEMO):
        self.proc = subprocess.Popen([sys.executable, script], stdin=subprocess.PIPE,
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
        self.assertEqual(list(tools), ["add", "typed", "manual"])
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
        self.assertEqual(props["extra"]["additionalProperties"], {"type": "integer"})
        self.assertEqual(tools["manual"]["inputSchema"]["properties"], {"x": {"type": "string"}})

    def test_protocol_errors(self):
        self.assertEqual(self.call("nope")["error"]["code"], -32601)
        self.assertEqual(self.call("ping", [1, 2])["error"]["code"], -32602)
        self.client.send_raw(b"{not json\n")
        self.assertEqual(self.client.recv()["error"]["code"], -32700)
        self.client.send_raw(b'[{"jsonrpc":"2.0","id":1,"method":"ping"}]\n')
        self.assertEqual(self.client.recv()["error"]["code"], -32600)
        self.assertEqual(self.call("ping")["result"], {})      # still alive

    def test_exits_when_stdin_closes(self):
        self.assertEqual(self.client.close(), 0)


if __name__ == "__main__":
    unittest.main()
