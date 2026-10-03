import test from "node:test";
import assert from "node:assert/strict";
import { ethers } from "ethers";
import { MAX_PATCH_BYTES, verifyPatchHash } from "../src/features/governance/patchVerify.ts";

const patch = new TextEncoder().encode("BSDIFF40 pretend patch bytes");
const goodHash = ethers.sha256(patch);
const URL_OK = "http://100.1.2.3:8000/patch_v1.1.bin";

const respond = (body: Uint8Array, init: { status?: number; headers?: Record<string, string> } = {}) =>
  (async () => new Response(body as BodyInit, { status: init.status ?? 200, headers: init.headers })) as unknown as typeof fetch;

test("matching bytes verify (hash given with or without 0x, any case)", async () => {
  for (const h of [goodHash, goodHash.slice(2), goodHash.toUpperCase().replace("0X", "0x")]) {
    const r = await verifyPatchHash(URL_OK, h, { fetchImpl: respond(patch) });
    assert.equal(r.status, "verified", h);
  }
});

test("tampered bytes are a mismatch and report both hashes", async () => {
  const evil = new TextEncoder().encode("BSDIFF40 different bytes");
  const r = await verifyPatchHash(URL_OK, goodHash, { fetchImpl: respond(evil) });
  assert.equal(r.status, "mismatch");
  assert.match(r.detail, /anchors/);
  assert.equal(r.actualHash, ethers.sha256(evil));
});

test("HTTP errors, network errors and timeouts are unreachable, never verified", async () => {
  assert.equal((await verifyPatchHash(URL_OK, goodHash, { fetchImpl: respond(patch, { status: 404 }) })).status, "unreachable");
  const boom = (async () => { throw new TypeError("fetch failed"); }) as unknown as typeof fetch;
  const net = await verifyPatchHash(URL_OK, goodHash, { fetchImpl: boom });
  assert.equal(net.status, "unreachable");
  assert.match(net.detail, /fetch failed/);
  const hang = ((_u: string, init?: RequestInit) =>
    new Promise((_res, rej) => init?.signal?.addEventListener("abort", () => rej(Object.assign(new Error("aborted"), { name: "AbortError" }))))) as unknown as typeof fetch;
  const slow = await verifyPatchHash(URL_OK, goodHash, { fetchImpl: hang, timeoutMs: 30 });
  assert.equal(slow.status, "unreachable");
  assert.match(slow.detail, /in time/);
});

test("oversized patches are refused before hashing", async () => {
  const r = await verifyPatchHash(URL_OK, goodHash, {
    fetchImpl: respond(patch, { headers: { "content-length": String(MAX_PATCH_BYTES + 1) } }),
  });
  assert.equal(r.status, "unreachable");
  assert.match(r.detail, /limit/);
});

test("bad inputs are unreachable with a reason", async () => {
  assert.equal((await verifyPatchHash("ipfs://Qm123", goodHash)).status, "unreachable");
  assert.equal((await verifyPatchHash("", goodHash)).status, "unreachable");
  assert.equal((await verifyPatchHash(URL_OK, "")).status, "unreachable");
});
