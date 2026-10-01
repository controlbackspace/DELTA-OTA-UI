"""Public-facing JSON-RPC filter for the Hardhat node (stdlib only).

The phone's MetaMask reaches the chain through a public HTTPS tunnel
(Tailscale Funnel, fixed URL). Exposing Hardhat directly would be unsafe:
its dev accounts are UNLOCKED, so anyone holding the URL could call
eth_sendTransaction *as* the authorized developers and propose/approve
releases without any wallet. This guard sits between the tunnel and the node
and forwards only what a wallet needs - reads, gas estimation, and
eth_sendRawTransaction (signed on the phone). Node-side signing, account
listing and hardhat_/evm_ admin methods are refused.

The desktop console keeps talking to 127.0.0.1:8545 directly (its dev
signers are local); only the tunnel points here.

Run:  python gateway/rpc_guard.py [--port 8546] [--upstream http://127.0.0.1:8545]
"""
import argparse
import http.server
import json
import sys
import urllib.error
import urllib.request

# Everything MetaMask (or any external wallet) needs against a custom network.
ALLOWED_METHODS = frozenset({
    "eth_chainId", "net_version", "net_listening", "web3_clientVersion",
    "eth_syncing", "eth_blockNumber", "eth_gasPrice", "eth_maxPriorityFeePerGas",
    "eth_feeHistory", "eth_getBalance", "eth_getCode", "eth_getStorageAt",
    "eth_getTransactionCount", "eth_call", "eth_estimateGas",
    "eth_sendRawTransaction", "eth_getTransactionByHash",
    "eth_getTransactionReceipt", "eth_getBlockByNumber", "eth_getBlockByHash",
    "eth_getLogs",
})
MAX_BODY_BYTES = 1024 * 1024
UPSTREAM_TIMEOUT_S = 30


def _refusal(req_id, method):
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601,
                      "message": f"Method {method!r} is not available on this public endpoint"}}


class GuardHandler(http.server.BaseHTTPRequestHandler):
    server_version = "DeltaOTA-RpcGuard/1.0"
    upstream = "http://127.0.0.1:8545"

    def _reply(self, status: int, payload) -> None:
        body = json.dumps(payload).encode() if payload is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _forward(self, payload):
        req = urllib.request.Request(
            self.upstream, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=UPSTREAM_TIMEOUT_S) as resp:
            return json.loads(resp.read())

    def do_GET(self):
        self._reply(200, {"service": "DeltaOTA JSON-RPC guard", "use": "POST JSON-RPC"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY_BYTES:
            self._reply(413 if length > MAX_BODY_BYTES else 400,
                        {"jsonrpc": "2.0", "id": None,
                         "error": {"code": -32600, "message": "Invalid request size"}})
            return
        try:
            request = json.loads(self.rfile.read(length))
        except ValueError:
            self._reply(400, {"jsonrpc": "2.0", "id": None,
                              "error": {"code": -32700, "message": "Parse error"}})
            return

        batch = isinstance(request, list)
        calls = request if batch else [request]
        allowed, refused = [], []
        for call in calls:
            method = call.get("method") if isinstance(call, dict) else None
            if method in ALLOWED_METHODS:
                allowed.append(call)
            else:
                refused.append(_refusal(call.get("id") if isinstance(call, dict) else None, method))
                print(f"[RpcGuard] Refused {method!r}")

        results = []
        if allowed:
            try:
                upstream = self._forward(allowed if batch else allowed[0])
            except (urllib.error.URLError, OSError, ValueError) as e:
                self._reply(502, {"jsonrpc": "2.0", "id": None,
                                  "error": {"code": -32603, "message": f"Node unreachable: {e}"}})
                return
            results = upstream if isinstance(upstream, list) else [upstream]

        if batch:
            self._reply(200, results + refused)
        else:
            self._reply(200, results[0] if results else refused[0])

    def log_message(self, *args):
        pass   # refusals are logged explicitly; per-call logs would flood the window


def main() -> int:
    parser = argparse.ArgumentParser(description="Public JSON-RPC filter for the Hardhat node.")
    parser.add_argument("--port", type=int, default=8546)
    parser.add_argument("--upstream", default="http://127.0.0.1:8545")
    args = parser.parse_args()
    GuardHandler.upstream = args.upstream
    # Loopback only: the tunnel client connects locally; nothing else should.
    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), GuardHandler)
    print(f"[RpcGuard] 127.0.0.1:{args.port} -> {args.upstream} "
          f"({len(ALLOWED_METHODS)} wallet methods allowed; node-side signing refused)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
