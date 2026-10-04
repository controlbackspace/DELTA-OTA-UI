import test from "node:test";
import assert from "node:assert/strict";
import { BrowserProvider } from "ethers";
import { createSplitProvider, isWalletMethod } from "../src/features/wallet/splitProvider.ts";

type Call = { method: string; params?: unknown };

function fakeWallet(answers: Record<string, unknown> = {}) {
  const calls: Call[] = [];
  const listeners: string[] = [];
  return {
    calls,
    listeners,
    request: async ({ method, params }: Call) => {
      calls.push({ method, params });
      if (method in answers) {
        const a = answers[method];
        if (a instanceof Error) throw a;
        return a;
      }
      throw new Error(`wallet should not be asked for ${method}`);
    },
    on: (event: string) => listeners.push(`on:${event}`),
    removeListener: (event: string) => listeners.push(`off:${event}`),
  };
}

function fakeNode(handlers: Record<string, unknown>, opts: { status?: number; fail?: boolean } = {}) {
  const requests: { url: string; body: { id: number; method: string; params: unknown } }[] = [];
  const impl = (async (url: string, init: RequestInit) => {
    if (opts.fail) throw new TypeError("Failed to fetch");
    const body = JSON.parse(String(init.body));
    requests.push({ url, body });
    if (opts.status && opts.status !== 200) return new Response("nope", { status: opts.status });
    const h = handlers[body.method];
    const payload =
      h instanceof Error
        ? { jsonrpc: "2.0", id: body.id, error: { code: 3, message: h.message, data: "0x08c379a0" } }
        : { jsonrpc: "2.0", id: body.id, result: h };
    return new Response(JSON.stringify(payload), { status: 200 });
  }) as unknown as typeof fetch;
  return { requests, impl };
}

test("wallet-only methods are recognised, reads are not", () => {
  for (const m of ["eth_chainId", "net_version", "eth_accounts", "eth_requestAccounts", "eth_sendTransaction",
    "personal_sign", "eth_signTypedData_v4", "wallet_switchEthereumChain", "wallet_addEthereumChain"]) {
    assert.equal(isWalletMethod(m), true, m);
  }
  for (const m of ["eth_blockNumber", "eth_estimateGas", "eth_call", "eth_getTransactionReceipt", "eth_gasPrice",
    "eth_getTransactionCount", "eth_getLogs", "eth_feeHistory", "eth_getBalance", "eth_getBlockByNumber"]) {
    assert.equal(isWalletMethod(m), false, m);
  }
});

test("reads go to the console's RPC, never to the wallet", async () => {
  const wallet = fakeWallet();
  const node = fakeNode({ eth_blockNumber: "0x2a", eth_estimateGas: "0x5208" });
  const p = createSplitProvider({ wallet, readUrl: "https://node.example.ts.net", fetchImpl: node.impl });
  assert.equal(await p.request({ method: "eth_blockNumber" }), "0x2a");
  assert.equal(await p.request({ method: "eth_estimateGas", params: [{ to: "0x0" }] }), "0x5208");
  assert.equal(wallet.calls.length, 0);
  assert.deepEqual(node.requests.map((r) => r.url), ["https://node.example.ts.net", "https://node.example.ts.net"]);
  assert.deepEqual(node.requests.map((r) => r.body.id), [1, 2], "ids increment");
  assert.deepEqual(node.requests[0].body.params, [], "missing params become []");
});

test("signing, accounts and chain id go to the wallet, never to the node", async () => {
  const wallet = fakeWallet({ eth_chainId: "0x7a69", eth_accounts: ["0xabc"], eth_sendTransaction: "0xhash" });
  const node = fakeNode({});
  const p = createSplitProvider({ wallet, readUrl: "http://127.0.0.1:8545", fetchImpl: node.impl });
  assert.equal(await p.request({ method: "eth_chainId" }), "0x7a69");
  assert.deepEqual(await p.request({ method: "eth_accounts" }), ["0xabc"]);
  assert.equal(await p.request({ method: "eth_sendTransaction", params: [{ to: "0x1" }] }), "0xhash");
  assert.equal(node.requests.length, 0);
  assert.deepEqual(wallet.calls[2], { method: "eth_sendTransaction", params: [{ to: "0x1" }] });
});

test("node errors keep code and data so reverts can be decoded", async () => {
  const p = createSplitProvider({ wallet: fakeWallet(), readUrl: "http://n", fetchImpl: fakeNode({ eth_call: new Error("execution reverted") }).impl });
  await assert.rejects(p.request({ method: "eth_call", params: [] }), (e: Error & { code?: number; data?: string }) => {
    assert.equal(e.message, "execution reverted");
    assert.equal(e.code, 3);
    assert.equal(e.data, "0x08c379a0");
    return true;
  });
});

test("an unreachable node surfaces as a read failure and the wallet is never involved", async () => {
  const wallet = fakeWallet();
  const p = createSplitProvider({ wallet, readUrl: "http://n", fetchImpl: fakeNode({}, { fail: true }).impl });
  await assert.rejects(p.request({ method: "eth_blockNumber" }), /Failed to fetch/);
  assert.equal(wallet.calls.length, 0);
});

test("an HTTP error names the RPC that failed", async () => {
  const p = createSplitProvider({ wallet: fakeWallet(), readUrl: "https://down.example", fetchImpl: fakeNode({}, { status: 502 }).impl });
  await assert.rejects(p.request({ method: "eth_blockNumber" }), /https:\/\/down\.example answered HTTP 502/);
});

test("wallet errors (user rejected) pass through untouched", async () => {
  const rejected = Object.assign(new Error("User rejected the request."), { code: 4001 });
  const p = createSplitProvider({ wallet: fakeWallet({ eth_sendTransaction: rejected }), readUrl: "http://n", fetchImpl: fakeNode({}).impl });
  await assert.rejects(p.request({ method: "eth_sendTransaction", params: [] }), (e: Error & { code?: number }) => e.code === 4001);
});

test("event subscriptions are delegated to the wallet", () => {
  const wallet = fakeWallet();
  const p = createSplitProvider({ wallet, readUrl: "http://n", fetchImpl: fakeNode({}).impl });
  p.on("accountsChanged", () => {});
  p.removeListener("accountsChanged", () => {});
  assert.deepEqual(wallet.listeners, ["on:accountsChanged", "off:accountsChanged"]);
  // a wallet without event support must not break the wrapper
  const bare = { request: async () => "0x1" } as never;
  const q = createSplitProvider({ wallet: bare, readUrl: "http://n" });
  assert.doesNotThrow(() => q.on("x", () => {}));
});

test("with ethers: the chain id comes from the phone, the block number from the node (the failing case)", async () => {
  const wallet = fakeWallet({ eth_chainId: "0x7a69", eth_accounts: ["0x70997970C51812dc3A010C7d01b50e0d17dc79C8"] });
  // Without the split, WalletConnect would have asked 127.0.0.1:8545 here and failed with "Failed to fetch".
  const node = fakeNode({ eth_blockNumber: "0x10" });
  const provider = new BrowserProvider(createSplitProvider({ wallet, readUrl: "https://node.example.ts.net", fetchImpl: node.impl }), 31337);
  assert.equal(await provider.getBlockNumber(), 16);
  assert.equal(Number((await provider.getNetwork()).chainId), 31337);
  assert.deepEqual(wallet.calls.map((c) => c.method).filter((m) => m !== "eth_chainId"), []);
  assert.ok(node.requests.every((r) => r.body.method !== "eth_chainId" && r.body.method !== "eth_accounts"));
});
