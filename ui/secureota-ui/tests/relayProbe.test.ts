import { test } from "node:test";
import assert from "node:assert/strict";
import { relayReachable } from "../src/features/wallet/relayProbe.ts";
import { isLocalNodeRpc } from "../src/features/governance/consoleConfig.ts";

test("relay probe: an answered request is reachable", async () => {
  const ok = await relayReachable({ fetchImpl: (async () => new Response("")) as typeof fetch });
  assert.equal(ok, true);
});

test("relay probe: a network failure is unreachable", async () => {
  const bad = await relayReachable({ fetchImpl: (async () => { throw new TypeError("Failed to fetch"); }) as typeof fetch });
  assert.equal(bad, false);
});

test("relay probe: a hung request times out as unreachable", async () => {
  const hang = ((_u: unknown, init?: RequestInit) =>
    new Promise((_r, rej) => init?.signal?.addEventListener("abort", () => rej(new Error("aborted"))))) as typeof fetch;
  assert.equal(await relayReachable({ fetchImpl: hang, timeoutMs: 20 }), false);
});

test("offline demo signers are allowed only on a local http node", () => {
  for (const u of ["http://127.0.0.1:8545", "http://localhost:8545", "http://192.168.50.1:8545", "http://10.10.10.2:8545", "http://172.20.1.5:8545", "http://100.101.102.103:8545"]) {
    assert.equal(isLocalNodeRpc(u), true, u);
  }
  for (const u of ["https://laptop.tail1234.ts.net", "http://8.8.8.8:8545", "http://172.32.0.1:8545", "https://127.0.0.1:8545", "http://example.com:8545"]) {
    assert.equal(isLocalNodeRpc(u), false, u);
  }
});
