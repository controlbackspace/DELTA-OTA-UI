/**
 * The per-run settings every author's console needs, as one pasteable line.
 * demo-up.bat prints it after deploying (the contract address changes on every
 * run; the Funnel URL does not). Pure functions - the wallet hook applies the
 * result through its existing validated setters.
 */

export interface ConsoleConfig {
  /** DeltaOTA contract address. */
  contract?: string;
  /** Node RPC this console reads the chain through (the Funnel URL on remote machines). */
  rpc?: string;
  /** HTTPS RPC the phone wallet uses (the same Funnel URL). */
  phoneRpc?: string;
  /** Gateway whose status feed to follow, e.g. the Pi's Tailscale IP. */
  gatewayHost?: string;
}

export type ParsedConfig =
  | { ok: true; config: ConsoleConfig; skipped: string[] }
  | { ok: false; error: string };

const ADDRESS = /^0x[0-9a-fA-F]{40}$/;
const HTTP_ORIGIN = /^https?:\/\/[^/\s]+(:\d+)?$/;
const HTTPS_ORIGIN = /^https:\/\/[^/\s]+$/;
const HOST = /^[A-Za-z0-9.-]+(:\d+)?$/;
const LOOPBACK = /^https?:\/\/(127\.\d+\.\d+\.\d+|localhost|\[::1\])(:\d+)?\/?$/i;

export const isLoopbackRpc = (url: string): boolean => LOOPBACK.test((url || "").trim());

const PRIVATE_NODE =
  /^http:\/\/(127\.\d+\.\d+\.\d+|localhost|\[::1\]|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+)(:\d+)?\/?$/i;

/** A node this console may sign on with its own unlocked accounts: plain http on
 *  loopback or a private LAN / tailnet address. A public https URL (Funnel) never
 *  qualifies - rpc_guard refuses node-side signing there by design. */
export const isLocalNodeRpc = (url: string): boolean => PRIVATE_NODE.test((url || "").trim());

/** Does a node answer chain 31337 at this address? Used to recognise the PC
 *  that RUNS the node: its console must keep reading 127.0.0.1:8545 instead of
 *  switching to the Funnel URL that only remote authors need. */
export async function localNodeAnswers(
  url: string,
  opts: { fetchImpl?: typeof fetch; timeoutMs?: number } = {}
): Promise<boolean> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 2500);
  try {
    const res = await (opts.fetchImpl ?? fetch)(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "eth_chainId", params: [] }),
      signal: ctrl.signal,
    });
    if (!res.ok) return false;
    const body = (await res.json()) as { result?: string };
    return body.result === "0x7a69";
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

const PREFIX = "DELTAOTA-CONFIG";

export function buildConsoleConfig(c: ConsoleConfig): string {
  return `${PREFIX} ${JSON.stringify({ v: 1, ...c })}`;
}

export function parseConsoleConfig(text: string): ParsedConfig {
  let body = (text || "").trim();
  if (body.startsWith(PREFIX)) body = body.slice(PREFIX.length).trim();
  if (!body) return { ok: false, error: "Nothing to import - paste the line printed by demo-up." };

  let raw: unknown;
  try {
    raw = JSON.parse(body);
  } catch {
    return { ok: false, error: "Not valid JSON - paste the whole DELTAOTA-CONFIG line from demo-up." };
  }
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return { ok: false, error: "Expected a JSON object." };
  }
  const o = raw as Record<string, unknown>;
  const config: ConsoleConfig = {};
  const skipped: string[] = [];

  const take = (key: keyof ConsoleConfig, valid: (v: string) => boolean, why: string, clean = (v: string) => v) => {
    const v = o[key];
    if (v === undefined || v === null || v === "") return;
    if (typeof v !== "string" || !valid(clean(v.trim()))) {
      skipped.push(`${key}: ${why}`);
      return;
    }
    config[key] = clean(v.trim());
  };
  const noSlash = (v: string) => v.replace(/\/+$/, "");

  take("contract", (v) => ADDRESS.test(v), "expected 0x + 40 hex characters");
  take("rpc", (v) => HTTP_ORIGIN.test(v), "expected http(s)://host[:port]", noSlash);
  take("phoneRpc", (v) => HTTPS_ORIGIN.test(v), "phone RPC must be https://host", noSlash);
  take("gatewayHost", (v) => HOST.test(v), "expected a host or IP, optionally :port");

  if (Object.keys(config).length === 0) {
    return { ok: false, error: `No usable setting found${skipped.length ? " (" + skipped.join("; ") + ")" : ""}.` };
  }
  return { ok: true, config, skipped };
}
