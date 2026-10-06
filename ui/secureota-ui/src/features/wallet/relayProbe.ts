/**
 * Can this machine reach the WalletConnect relay? The phone-wallet path needs it
 * (both the console and the phone talk to the relay); nothing else in the
 * pipeline does. Used only to decide whether to *offer* the offline demo
 * signers - never to switch to them silently.
 */
export const RELAY_URL = "https://relay.walletconnect.com";

export async function relayReachable(
  opts: { fetchImpl?: typeof fetch; timeoutMs?: number; url?: string } = {}
): Promise<boolean> {
  if (typeof navigator !== "undefined" && navigator.onLine === false) return false;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 3000);
  try {
    // no-cors: an opaque response still proves the host answered.
    await (opts.fetchImpl ?? fetch)(opts.url ?? RELAY_URL, { method: "GET", mode: "no-cors", cache: "no-store", signal: ctrl.signal });
    return true;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}
