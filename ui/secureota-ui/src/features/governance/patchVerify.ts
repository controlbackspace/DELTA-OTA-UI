/**
 * An approver's own check of what they are about to sign: download the patch
 * from the URL anchored on-chain and compare its SHA-256 with the on-chain
 * golden hash. The hash covers the patch bytes themselves, so no base binary
 * is needed - any author can do this from any machine that can reach the URL.
 *
 * Outcomes: "verified" (match), "mismatch" (the bytes at that URL are NOT what
 * the proposer anchored - block the approval), "unreachable" (could not
 * check - warn and require an explicit override).
 */
import { ethers } from "ethers";

export type PatchCheckStatus = "verified" | "mismatch" | "unreachable";

export interface PatchCheck {
  status: PatchCheckStatus;
  detail: string;
  actualHash?: string;
}

/** Same cap as the gateway's MAX_DOWNLOAD_BYTES: refuse unbounded downloads. */
export const MAX_PATCH_BYTES = 8 * 1024 * 1024;

const normalizeHash = (h: string): string => {
  const low = (h || "").trim().toLowerCase();
  return low && !low.startsWith("0x") ? `0x${low}` : low;
};

export async function verifyPatchHash(
  url: string,
  expectedHash: string,
  opts: { fetchImpl?: typeof fetch; timeoutMs?: number } = {}
): Promise<PatchCheck> {
  const expected = normalizeHash(expectedHash);
  if (!expected) return { status: "unreachable", detail: "No golden hash is recorded on-chain for this release." };
  if (!/^https?:\/\/[^\s]+$/i.test(url || "")) {
    return { status: "unreachable", detail: `The on-chain URL is not an http(s) address: "${url || ""}".` };
  }

  const doFetch = opts.fetchImpl ?? fetch;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 15000);
  try {
    const res = await doFetch(url, { signal: ctrl.signal, cache: "no-store" });
    if (!res.ok) return { status: "unreachable", detail: `The patch host answered HTTP ${res.status}.` };
    const declared = Number(res.headers.get("content-length") ?? 0);
    if (declared > MAX_PATCH_BYTES) {
      return { status: "unreachable", detail: `The patch is ${declared} bytes - over the ${MAX_PATCH_BYTES} byte limit.` };
    }
    const bytes = new Uint8Array(await res.arrayBuffer());
    if (bytes.length > MAX_PATCH_BYTES) {
      return { status: "unreachable", detail: `The patch is over the ${MAX_PATCH_BYTES} byte limit.` };
    }
    const actual = ethers.sha256(bytes).toLowerCase();
    if (actual === expected) {
      return { status: "verified", detail: `SHA-256 matches the on-chain golden hash (${bytes.length} bytes).`, actualHash: actual };
    }
    return {
      status: "mismatch",
      detail: `The bytes at the URL hash to ${actual}, but the chain anchors ${expected}.`,
      actualHash: actual,
    };
  } catch (err) {
    const aborted = err instanceof Error && err.name === "AbortError";
    return {
      status: "unreachable",
      detail: aborted
        ? "The patch host did not answer in time (is the proposer's PC on, reachable over Tailscale/LAN, and serve_artifacts running?)."
        : `Could not download the patch (${err instanceof Error ? err.message : "network error"}).`,
    };
  } finally {
    clearTimeout(timer);
  }
}
