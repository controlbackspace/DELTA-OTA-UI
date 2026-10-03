import test from "node:test";
import assert from "node:assert/strict";
import { buildConsoleConfig, isLoopbackRpc, parseConsoleConfig } from "../src/features/governance/consoleConfig.ts";

const CONTRACT = "0x5FbDB2315678afecb367f032d93F642f64180aa3";

test("round trip of the line demo-up prints", () => {
  const line = buildConsoleConfig({
    contract: CONTRACT,
    rpc: "https://kinx.tail9ee3ca.ts.net",
    phoneRpc: "https://kinx.tail9ee3ca.ts.net",
    gatewayHost: "100.101.102.103",
  });
  assert.ok(line.startsWith("DELTAOTA-CONFIG {"));
  const r = parseConsoleConfig(line);
  assert.equal(r.ok, true);
  if (r.ok) {
    assert.equal(r.config.contract, CONTRACT);
    assert.equal(r.config.rpc, "https://kinx.tail9ee3ca.ts.net");
    assert.equal(r.config.gatewayHost, "100.101.102.103");
    assert.deepEqual(r.skipped, []);
  }
});

test("raw JSON without the prefix, trailing slash and whitespace are tolerated", () => {
  const r = parseConsoleConfig(`  {"contract":"${CONTRACT}","rpc":"https://h.ts.net/ "}  `);
  assert.equal(r.ok, true);
  if (r.ok) assert.equal(r.config.rpc, "https://h.ts.net");
});

test("bad fields are skipped individually, good ones still apply", () => {
  const r = parseConsoleConfig(`{"contract":"0x123","rpc":"https://h.ts.net","phoneRpc":"http://h.ts.net","gatewayHost":"a b"}`);
  assert.equal(r.ok, true);
  if (r.ok) {
    assert.deepEqual(Object.keys(r.config), ["rpc"]);
    assert.equal(r.skipped.length, 3);
  }
});

test("garbage is rejected with a reason", () => {
  for (const bad of ["", "   ", "not json", "[]", "null", `{"contract":"nope"}`, `{"x":1}`]) {
    const r = parseConsoleConfig(bad);
    assert.equal(r.ok, false, JSON.stringify(bad));
    if (!r.ok) assert.ok(r.error.length > 0);
  }
});

test("loopback detection decides whether the dev signer can exist", () => {
  for (const u of ["http://127.0.0.1:8545", "http://localhost:8545", "https://127.0.0.1", "http://[::1]:8545/"]) {
    assert.equal(isLoopbackRpc(u), true, u);
  }
  for (const u of ["https://kinx.tail9ee3ca.ts.net", "http://192.168.1.5:8545", "http://100.64.0.1:8545"]) {
    assert.equal(isLoopbackRpc(u), false, u);
  }
});

test("the exact lines scripts/demo-up.bat prints import cleanly (with and without gateway)", () => {
  const plain = `DELTAOTA-CONFIG {"v":1,"contract":"${CONTRACT}","rpc":"https://kinx.tail9ee3ca.ts.net","phoneRpc":"https://kinx.tail9ee3ca.ts.net"}`;
  const withGw = plain.replace(/}$/, `,"gatewayHost":"100.101.102.103"}`);
  const a = parseConsoleConfig(plain);
  const b = parseConsoleConfig(withGw + "\r\n"); // batch redirect leaves CRLF
  assert.equal(a.ok && a.config.gatewayHost, undefined);
  assert.equal(b.ok && b.config.gatewayHost, "100.101.102.103");
  assert.equal(a.ok && a.skipped.length, 0);
});

import { localNodeAnswers } from "../src/features/governance/consoleConfig.ts";

const rpcReply = (result: string, ok = true) =>
  (async () => ({ ok, json: async () => ({ result }) })) as unknown as typeof fetch;

test("the node host is recognised by a local chain-31337 answer; anything else is not", async () => {
  assert.equal(await localNodeAnswers("http://127.0.0.1:8545", { fetchImpl: rpcReply("0x7a69") }), true);
  assert.equal(await localNodeAnswers("http://127.0.0.1:8545", { fetchImpl: rpcReply("0x1") }), false, "wrong chain");
  assert.equal(await localNodeAnswers("http://127.0.0.1:8545", { fetchImpl: rpcReply("0x7a69", false) }), false, "HTTP error");
  const refused = (async () => { throw new TypeError("fetch failed"); }) as unknown as typeof fetch;
  assert.equal(await localNodeAnswers("http://127.0.0.1:8545", { fetchImpl: refused }), false, "no local node = a remote author");
  const hang = ((_u: string, init?: RequestInit) =>
    new Promise((_r, rej) => init?.signal?.addEventListener("abort", () => rej(new Error("aborted"))))) as unknown as typeof fetch;
  assert.equal(await localNodeAnswers("http://127.0.0.1:8545", { fetchImpl: hang, timeoutMs: 30 }), false, "timeout");
});
