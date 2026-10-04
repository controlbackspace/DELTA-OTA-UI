/**
 * An EIP-1193 provider that sends wallet-only methods to the wallet and every
 * read to the console's own RPC.
 *
 * Why: the WalletConnect provider answers reads (eth_blockNumber, eth_estimateGas,
 * eth_call, receipt polling) itself from the chain's built-in RPC map, which for
 * Hardhat is http://127.0.0.1:8545. That only works on the PC that runs the
 * node; on any other machine the page's fetch fails ("Failed to fetch") before
 * the phone is even asked to sign. The console already knows the right node
 * (the Funnel URL on a remote machine), so reads go there. Signing and account
 * questions stay with the wallet, and eth_chainId stays with the wallet so the
 * "is the phone on chain 31337?" check still reflects the phone.
 */
import type { Eip1193Provider } from "ethers";

const WALLET_METHODS = new Set([
  "eth_chainId",
  "net_version",
  "eth_accounts",
  "eth_requestAccounts",
  "eth_sendTransaction",
  "eth_signTransaction",
  "eth_sign",
  "personal_sign",
]);

/** True for methods only the wallet can answer (accounts, signing, chain/session state). */
export const isWalletMethod = (method: string): boolean =>
  WALLET_METHODS.has(method) ||
  method.startsWith("eth_signTypedData") ||
  method.startsWith("personal_") ||
  method.startsWith("wallet_");

export interface SplitProviderOptions {
  wallet: Eip1193Provider;
  /** JSON-RPC endpoint every read goes to. */
  readUrl: string;
  fetchImpl?: typeof fetch;
}

export type SplitProvider = Eip1193Provider & {
  on: (event: string, listener: (...args: unknown[]) => void) => void;
  removeListener: (event: string, listener: (...args: unknown[]) => void) => void;
};

type Listening = {
  on?: (event: string, listener: (...args: unknown[]) => void) => unknown;
  removeListener?: (event: string, listener: (...args: unknown[]) => void) => unknown;
};

export function createSplitProvider({ wallet, readUrl, fetchImpl }: SplitProviderOptions): SplitProvider {
  let nextId = 0;

  async function read(method: string, params: unknown) {
    const res = await (fetchImpl ?? fetch)(readUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: ++nextId, method, params: params ?? [] }),
    });
    if (!res.ok) {
      throw Object.assign(new Error(`The RPC at ${readUrl} answered HTTP ${res.status}`), { code: -32603 });
    }
    const body = (await res.json()) as { result?: unknown; error?: { code?: number; message?: string; data?: unknown } };
    if (body.error) {
      // Keep code/data so ethers can still decode a revert reason.
      throw Object.assign(new Error(body.error.message ?? "RPC error"), { code: body.error.code, data: body.error.data });
    }
    return body.result;
  }

  const listening = wallet as unknown as Listening;
  return {
    request: ({ method, params }) => (isWalletMethod(method) ? wallet.request({ method, params }) : read(method, params)),
    on: (event, listener) => {
      listening.on?.(event, listener);
    },
    removeListener: (event, listener) => {
      listening.removeListener?.(event, listener);
    },
  };
}
