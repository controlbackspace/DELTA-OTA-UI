import { useEffect, useState } from "react";

/**
 * Live gateway status (gateway/secureota/gateway_runtime/gateway_status.py),
 * exposed by the artifact server as /gateway_status.json. Reporting only:
 * the console never decides anything from it — it shows what the gateway
 * and device are really doing.
 */
export interface GatewayStatus {
  gateway_state?:
    | "starting"
    | "waiting"
    | "unreachable"
    | "staged"
    | "revoked"
    | "hash-mismatch"
    | "download-failed"
    | "invalid-payload";
  target_version?: string | null;
  staged_version?: string | null;
  blocks_total?: number | null;
  contract?: string;
  key_fp?: string;
  device_ip?: string | null;
  device_last_block?: number | null;
  device_final_sent?: boolean;
  device_last_seen?: number | null;
  device_reported_version?: string | null;
  device_reported_ip?: string | null;
  device_reported_at?: number | null;
  staged_at?: number | null;
  updated_at?: number;
}

const POLL_MS = 2000;
// The gateway loop rewrites the file every poll (5 s); older than this means
// the gateway process is gone, even if the artifact server still answers.
const STALE_AFTER_MS = 20000;
const DEFAULT_ARTIFACT_ORIGIN = "http://127.0.0.1:8000";

/** The artifact server that hosts the patch also hosts the status file, so
 *  derive its origin from the release's patch URL (falls back to localhost). */
export function statusUrlFor(patchUrl: string | null): string {
  let origin = DEFAULT_ARTIFACT_ORIGIN;
  if (patchUrl) {
    try {
      const parsed = new URL(patchUrl);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") origin = parsed.origin;
    } catch {
      // keep default
    }
  }
  return `${origin}/gateway_status.json`;
}

export function useGatewayStatus(statusUrl: string) {
  const [status, setStatus] = useState<GatewayStatus | null>(null);
  const [reachable, setReachable] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetch(statusUrl, { cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const body = (await res.json()) as GatewayStatus;
        if (cancelled) return;
        setStatus(body);
        setReachable(true);
      } catch {
        if (!cancelled) setReachable(false);
      } finally {
        if (!cancelled) setNow(Date.now());
      }
    };
    void poll();
    const id = window.setInterval(() => void poll(), POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [statusUrl]);

  const online =
    reachable &&
    typeof status?.updated_at === "number" &&
    now - status.updated_at * 1000 < STALE_AFTER_MS;

  return { status, online, reachable };
}
