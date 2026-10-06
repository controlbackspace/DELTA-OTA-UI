/**
 * Download a release's delta patch from the address the proposer anchored on the
 * ledger and check it against the ledger's golden hash. Pure helpers (fetch is
 * injectable) so the dialog stays thin and the logic is unit-tested.
 */
import { ethers } from "ethers";

/** Same cap the gateway applies to a downloaded patch. */
export const MAX_PATCH_BYTES = 8 * 1024 * 1024;

export type PatchFailure = "no-url" | "bad-url" | "unreachable" | "not-found" | "too-large" | "timeout";

export class PatchFetchError extends Error {
  readonly kind: PatchFailure;
  constructor(kind: PatchFailure, message: string) {
    super(message);
    this.kind = kind;
  }
}

export type ParsedPatchUrl =
  | { ok: true; href: string; host: string; fileName: string }
  | { ok: false; reason: "no-url" | "bad-url" };

export function parsePatchUrl(raw: string | null | undefined): ParsedPatchUrl {
  const text = (raw ?? "").trim();
  if (!text) return { ok: false, reason: "no-url" };
  try {
    const u = new URL(text);
    if (u.protocol !== "http:" && u.protocol !== "https:") return { ok: false, reason: "bad-url" };
    const fileName = decodeURIComponent(u.pathname.split("/").filter(Boolean).pop() ?? "") || "patch.bin";
    return { ok: true, href: u.href, host: u.host, fileName };
  } catch {
    return { ok: false, reason: "bad-url" };
  }
}

/** A plain-language hint about where the file lives. */
export function describeSource(host: string): string {
  const name = host.replace(/:\d+$/, "");
  if (/^(127\.|localhost$|\[::1\]$)/i.test(name)) return "This computer";
  if (/^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(name)) return "Local network";
  return "Remote server";
}

export const normalizeHash = (h: string): string => (h || "").trim().toLowerCase().replace(/^0x/, "");

export function sha256Hex(bytes: Uint8Array): string {
  return normalizeHash(ethers.sha256(bytes));
}

export interface VerifyResult {
  match: boolean;
  actual: string;
  expected: string;
  size: number;
}

export function compareToLedger(bytes: Uint8Array, ledgerHash: string): VerifyResult {
  const actual = sha256Hex(bytes);
  const expected = normalizeHash(ledgerHash);
  return { match: actual === expected && expected.length === 64, actual, expected, size: bytes.length };
}

export async function fetchPatchBytes(
  href: string,
  opts: { fetchImpl?: typeof fetch; timeoutMs?: number; maxBytes?: number } = {}
): Promise<Uint8Array> {
  const max = opts.maxBytes ?? MAX_PATCH_BYTES;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 15000);
  try {
    let res: Response;
    try {
      res = await (opts.fetchImpl ?? fetch)(href, { cache: "no-store", signal: ctrl.signal });
    } catch (err) {
      if (ctrl.signal.aborted) throw new PatchFetchError("timeout", "The download timed out.");
      throw new PatchFetchError("unreachable", err instanceof Error ? err.message : "Network error");
    }
    if (!res.ok) throw new PatchFetchError("not-found", `The server answered ${res.status}.`);
    const declared = Number(res.headers.get("content-length") ?? 0);
    if (declared > max) throw new PatchFetchError("too-large", "The file is larger than the allowed patch size.");
    const buf = new Uint8Array(await res.arrayBuffer());
    if (buf.length > max) throw new PatchFetchError("too-large", "The file is larger than the allowed patch size.");
    return buf;
  } catch (err) {
    if (err instanceof PatchFetchError) throw err;
    if (ctrl.signal.aborted) throw new PatchFetchError("timeout", "The download timed out.");
    throw new PatchFetchError("unreachable", err instanceof Error ? err.message : "Network error");
  } finally {
    clearTimeout(timer);
  }
}

/** Operator-friendly wording for each way the download can fail. */
export function failureText(kind: PatchFailure, host: string): string {
  switch (kind) {
    case "no-url":
      return "This release has no download address recorded on the ledger.";
    case "bad-url":
      return "The address recorded for this release is not a web link, so it cannot be downloaded here.";
    case "not-found":
      return `The server at ${host} answered, but the file is not there. The proposer's artifact server may have been restarted or cleaned.`;
    case "too-large":
      return "The file is larger than a delta patch should be, so it was not downloaded.";
    case "timeout":
    case "unreachable":
    default:
      return `Could not reach ${host}. Check that you are on the same network as the proposer's computer and that its artifact server is running.`;
  }
}

export const formatHashShort = (hex: string): string => {
  const h = normalizeHash(hex);
  return h.length > 20 ? `${h.slice(0, 10)}...${h.slice(-8)}` : h;
};
