"""JSON-RPC stdio client for the paper-search MCP CLI.

Usage:
  python mcp_client.py --list-tools
  python mcp_client.py '{"tool":"search_crossref","args":{"query":"...","max_results":50}}'
"""
import glob
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time


def find_exe():
    """Locate the paper-search MCP CLI without assuming the Python minor version."""
    env = os.environ.get("PAPER_SEARCH_MCP")
    if env:
        return env
    appdata = os.path.expandvars(r"%APPDATA%")
    pats = [os.path.join(appdata, "Python", "*", "Scripts", "paper-search-mcp.exe"),
            os.path.join(appdata, "Python", "*", "Scripts", "paper_search_mcp.exe"),
            os.path.expanduser(r"~\AppData\Roaming\Python\*\Scripts\paper-search-mcp.exe")]
    for pat in pats:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return shutil.which("paper-search-mcp") or os.path.join(appdata, "missing")


class McpClient:
    def __init__(self, exe=None, timeout=30):
        exe = exe or find_exe()
        if not os.path.exists(exe):
            raise SystemExit(
                "paper-search-mcp CLI not found at %s\n"
                "Set PAPER_SEARCH_MCP to the executable path." % exe
            )
        self.p = subprocess.Popen(
            [exe],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self.q = queue.Queue()
        threading.Thread(target=self._reader, daemon=True).start()
        self._send({
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pipeline", "version": "1"},
            },
        })
        self._until(0, timeout)
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._id = 0

    def _reader(self):
        for line in self.p.stdout:
            try:
                self.q.put(json.loads(line.decode("utf-8", errors="replace")))
            except Exception:
                pass

    def _send(self, msg):
        self.p.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
        self.p.stdin.flush()

    def _until(self, mid, timeout):
        end = time.time() + timeout
        while time.time() < end:
            try:
                m = self.q.get(timeout=max(0.1, end - time.time()))
            except queue.Empty:
                return None
            if m.get("id") == mid:
                return m

    def call(self, tool, args, timeout=120):
        self._id += 1
        mid = self._id
        self._send({
            "jsonrpc": "2.0", "id": mid, "method": "tools/call",
            "params": {"name": tool, "arguments": args},
        })
        r = self._until(mid, timeout)
        if r is None:
            return None
        if "error" in r:
            return "MCP_ERROR " + json.dumps(r["error"])
        return "\n".join(
            it.get("text", "")
            for it in r.get("result", {}).get("content", [])
            if it.get("type") == "text"
        )

    def list_tools(self, timeout=60):
        self._id += 1
        mid = self._id
        self._send({"jsonrpc": "2.0", "id": mid, "method": "tools/list", "params": {}})
        r = self._until(mid, timeout)
        return [t["name"] for t in r.get("result", {}).get("tools", [])] if r else []

    def close(self):
        try:
            self.p.stdin.close()
            self.p.terminate()
        except Exception:
            pass


def decode_stream(text):
    """Parse concatenated JSON objects from tool output into records."""
    recs, dec, i = [], json.JSONDecoder(), 0
    while i < len(text):
        while i < len(text) and text[i] in " \n\r\t":
            i += 1
        if i >= len(text):
            break
        try:
            obj, j = dec.raw_decode(text, i)
            recs.append(obj)
            i = j
        except Exception:
            nxt = text.find("{", i)
            if nxt == -1:
                break
            i = nxt
    return recs


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) > 1 and sys.argv[1] == "--list-tools":
        c = McpClient()
        names = c.list_tools()
        print(len(names), "tools")
        print(", ".join(sorted(names)))
        c.close()
    else:
        q = json.loads(sys.argv[1])
        c = McpClient()
        print(c.call(q["tool"], q.get("args", {}), q.get("timeout", 120)))
        c.close()
