import test from "node:test";
import assert from "node:assert/strict";
import { ethers } from "ethers";
import {
  PatchFetchError,
  compareToLedger,
  describeSource,
  failureText,
  fetchPatchBytes,
  formatHashShort,
  normalizeHash,
  parsePatchUrl,
} from "../src/features/governance/patchVerify.ts";

const bytes = new TextEncoder().encode("delta patch bytes");
const goodHash = ethers.sha256(bytes);

test("a release URL is split into host and file name", () => {
  const p = parsePatchUrl("http://192.168.100.94:8000/patch_v1.1.bin");
  assert.deepEqual(p, {
    ok: true,
    href: "http://192.168.100.94:8000/patch_v1.1.bin",
    host: "192.168.100.94:8000",
    fileName: "patch_v1.1.bin",
  });
});

test("missing and non-web addresses are reported, not guessed", () => {
  assert.deepEqual(parsePatchUrl(""), { ok: false, reason: "no-url" });
  assert.deepEqual(parsePatchUrl(undefined), { ok: false, reason: "no-url" });
  assert.deepEqual(parsePatchUrl("ipfs://Qm123"), { ok: false, reason: "bad-url" });
  assert.deepEqual(parsePatchUrl("not a url"), { ok: false, reason: "bad-url" });
});

test("the source is described in plain words", () => {
  assert.equal(describeSource("127.0.0.1:8000"), "This computer");
  assert.equal(describeSource("192.168.100.94:8000"), "Local network");
  assert.equal(describeSource("10.10.10.2:8000"), "Local network");
  assert.equal(describeSource("example.com"), "Remote server");
});

test("hash comparison ignores the 0x prefix and case, and rejects a different file", () => {
  assert.equal(compareToLedger(bytes, goodHash).match, true);
  assert.equal(compareToLedger(bytes, goodHash.toUpperCase().replace("0X", "0x")).match, true);
  assert.equal(compareToLedger(bytes, normalizeHash(goodHash)).match, true);
  const tampered = new Uint8Array(bytes);
  tampered[0] ^= 1;
  const r = compareToLedger(tampered, goodHash);
  assert.equal(r.match, false);
  assert.equal(r.size, bytes.length);
});

test("an empty or malformed ledger hash never matches", () => {
  assert.equal(compareToLedger(bytes, "").match, false);
  assert.equal(compareToLedger(bytes, "0x1234").match, false);
});

test("fetch returns the bytes on success", async () => {
  const fetchImpl = (async () => new Response(bytes)) as typeof fetch;
  assert.deepEqual(await fetchPatchBytes("http://h/x.bin", { fetchImpl }), bytes);
});

test("fetch failures are classified", async () => {
  const notFound = (async () => new Response("no", { status: 404 })) as typeof fetch;
  await assert.rejects(
    fetchPatchBytes("http://h/x", { fetchImpl: notFound }),
    (e: unknown) => e instanceof PatchFetchError && e.kind === "not-found"
  );
  const down = (async () => {
    throw new TypeError("Failed to fetch");
  }) as typeof fetch;
  await assert.rejects(
    fetchPatchBytes("http://h/x", { fetchImpl: down }),
    (e: unknown) => e instanceof PatchFetchError && e.kind === "unreachable"
  );
  const hang = ((_u: unknown, init?: RequestInit) =>
    new Promise((_r, rej) => init?.signal?.addEventListener("abort", () => rej(new Error("aborted"))))) as typeof fetch;
  await assert.rejects(
    fetchPatchBytes("http://h/x", { fetchImpl: hang, timeoutMs: 20 }),
    (e: unknown) => e instanceof PatchFetchError && e.kind === "timeout"
  );
  const big = (async () => new Response(new Uint8Array(50))) as typeof fetch;
  await assert.rejects(
    fetchPatchBytes("http://h/x", { fetchImpl: big, maxBytes: 10 }),
    (e: unknown) => e instanceof PatchFetchError && e.kind === "too-large"
  );
});

test("failure wording names the host and gives the next step", () => {
  assert.match(failureText("unreachable", "192.168.1.5:8000"), /192\.168\.1\.5:8000.*same network/);
  assert.match(failureText("no-url", ""), /no download address/);
});

test("hash short form keeps both ends", () => {
  assert.equal(formatHashShort("0x" + "ab".repeat(32)), "ababababab...abababab");
});
