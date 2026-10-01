import { useState, useCallback, useEffect } from "react";
import { ethers } from "ethers";
import { createAppKit } from "@reown/appkit/react";
import { defineChain, sepolia } from "@reown/appkit/networks";
import { EthersAdapter } from "@reown/appkit-adapter-ethers";
import {
  DELTA_OTA_ABI,
  DEFAULT_CONTRACT_ADDRESS,
  HARDHAT_AUTHORIZED_DEVS,
} from "../../contracts/deltaOta";
import {
  formatVersionBytes32,
  formatGoldenHashBytes32,
  truncateAddress,
} from "../../lib/web3Payloads";
import { getDesktopBridge } from "../../lib/desktop";

// WalletConnect Project ID for Reown AppKit (public client identifier —
// shipped in the bundle by design, not a secret). Env override wins when set.
export const REOWN_PROJECT_ID =
  (import.meta as unknown as { env: Record<string, string> }).env?.VITE_REOWN_PROJECT_ID ||
  "77a796e27254e03bf5ae9b9aba69b93b";

// Hardhat Localhost chain id (single source of truth for guards below)
export const HARDHAT_CHAIN_ID = 31337;

// Define network definition for AppKit (CAIP-identified custom chain —
// chainNamespace + caipNetworkId are required: without them the WC session
// proposal carries an unresolvable chain and phone wallets spin forever).
export const localhostNetwork = defineChain({
  id: 31337,
  chainNamespace: "eip155",
  caipNetworkId: "eip155:31337",
  name: "Hardhat Localhost",
  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
  rpcUrls: {
    default: { http: ["http://127.0.0.1:8545"] },
  },
  testnet: true,
});

// Singleton AppKit instance
let appKitInstance: ReturnType<typeof createAppKit> | null = null;

// Guards ensurePhoneChain: one steering attempt per connected address (the
// wallet answers with prompts, not events — retrying per state tick would
// spam the phone). Reset on disconnect so a fresh session steers again.
let lastChainEnsureAddr: string | null = null;

// Single AppKit state subscription — openWalletModal runs on every retry
// click, so the previous listener is dropped before re-subscribing.
let modalStateUnsub: (() => void) | null = null;

// WalletConnect internals the guards below need. getWalletProvider() returns
// the UniversalProvider for QR sessions, which answers eth_chainId and
// eth_accounts LOCALLY — only client.ping and wallet requests reach the phone.
interface WcProviderInternals {
  client?: { ping(params: { topic: string }): Promise<void> };
  session?: { topic: string; namespaces?: Record<string, { accounts?: string[] }> };
}
const asWcInternals = (wp: unknown): WcProviderInternals | null =>
  wp && typeof wp === "object" && "client" in wp ? (wp as WcProviderInternals) : null;

/** MetaMask Mobile requires an HTTPS RPC for custom networks. */
const isPhoneRpcUrl = (url: string): boolean => /^https:\/\/[^/\s]+$/.test(url);

/** Hardhat serves plain HTTP: https:// on a loopback host never answers
 *  (usually the tunnel's scheme pasted into the Node RPC field). */
export const isHttpsLoopback = (url: string): boolean =>
  /^https:\/\/(127\.\d+\.\d+\.\d+|localhost|\[::1\])(:\d+)?\/?$/i.test(url.trim());

export function getAppKit() {
  if (typeof window === "undefined") return null;
  if (!appKitInstance) {
    try {
      const ethersAdapter = new EthersAdapter();
      appKitInstance = createAppKit({
        adapters: [ethersAdapter],
        // Sepolia is a pairing anchor only: a proposal offering just a custom
        // chain leaves MetaMask Mobile nothing it can approve unless 31337 is
        // already configured on the phone, and the scan spins forever. With a
        // well-known chain present the session always lands; ensurePhoneChain
        // then steers the phone to 31337, and getSigner refuses any other chain.
        networks: [localhostNetwork, sepolia],
        defaultNetwork: localhostNetwork,
        metadata: {
          name: "SecureOTA Console",
          description: "Blockchain-Secured IoT Firmware OTA Console",
          url: "https://secureota.local",
          icons: ["https://avatars.githubusercontent.com/u/37784886"],
        },
        projectId: REOWN_PROJECT_ID,
        features: {
          analytics: false,
          email: false,
          socials: [],
        },
        themeMode: "dark",
      });
    } catch (e) {
      console.warn("Could not initialize Reown AppKit:", e);
    }
  }
  return appKitInstance;
}

/** Bounded wait: closings, prompts, and handshakes must never hang the UI. */
const raceTimeout = <T,>(p: Promise<T>, ms: number, label: string): Promise<T> =>
  Promise.race([
    p,
    new Promise<never>((_, reject) =>
      window.setTimeout(() => reject(new Error(label)), ms)
    ),
  ]);

/** Chain IDs arrive in three shapes: number (31337), numeric string ("31337"),
 *  CAIP ("eip155:31337"). Garbage yields null — never NaN (NaN !== 31337 is
 *  always true and would wedge every chain gate permanently). */
const parseChainId = (v: string | number | undefined): number | null => {
  if (v === undefined || v === null) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  const tail = v.split(":").pop()?.trim() ?? "";
  const n = Number(tail);
  return tail !== "" && Number.isFinite(n) ? n : null;
};

/** Which key actually signed: phone wallet, browser extension, or node fallback. */
export type SignerOrigin = "wallet" | "injected" | "dev-node";

export interface ContractTransactionReceipt {
  hash: string;
  blockNumber: number;
  from: string;
  origin: SignerOrigin;
}

/** Structured on-chain release state — P0-2 chain-as-truth record. */
export interface OnChainReleaseRecord {
  version: string;
  goldenHash: string;
  ipfsUrl: string;
  approvalCount: number;
  isLive: boolean;
  isRevoked: boolean;
}

export function useDesktopWallet() {
  const [address, setAddress] = useState<string | null>(null);
  const [chainId, setChainId] = useState<number | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isConnecting, setIsConnecting] = useState<boolean>(false);
  const [connectionUri, setConnectionUri] = useState<string | null>(null);
  const [isQrModalOpen, setIsQrModalOpen] = useState<boolean>(false);
  const [contractAddress, setContractAddress] = useState<string>(() => {
    const stored = localStorage.getItem("SECUREOTA_CONTRACT_ADDRESS");
    // P0-3: localStorage override path covered — garbage never becomes truth.
    if (stored && stored.trim() && ethers.isAddress(stored.trim())) {
      try {
        return ethers.getAddress(stored.trim());
      } catch {
        // Fall through to default below.
      }
    }
    return DEFAULT_CONTRACT_ADDRESS;
  });
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // LAN RPC endpoint (P1 real-life): default localhost, overridable so a
  // second laptop can point its UI at the presenting machine's node.
  const [rpcUrl, setRpcUrl] = useState<string>(() => {
    try {
      const stored = localStorage.getItem("SECUREOTA_RPC_URL");
      if (
        stored &&
        stored.trim() &&
        /^https?:\/\/.+/.test(stored.trim()) &&
        !isHttpsLoopback(stored)
      ) {
        return stored.trim();
      }
    } catch {
      // ignore — default below
    }
    return "http://127.0.0.1:8545";
  });

  // Strict validation: malformed input is rejected loudly, never persisted.
  const updateRpcUrl = useCallback((url: string) => {
    const clean = (url || "").trim().replace(/\/+$/, "");
    if (!clean || !/^https?:\/\/[^/]+(:\d+)?$/.test(clean)) {
      setStatusMessage(
        `Invalid RPC URL rejected: "${url}" — expected http(s)://host[:port]; keeping current endpoint.`
      );
      return;
    }
    if (isHttpsLoopback(clean)) {
      setStatusMessage(
        `RPC URL rejected: "${clean}" — the local Hardhat node speaks plain http; use http://127.0.0.1:8545 (https tunnel URLs belong in Phone RPC).`
      );
      return;
    }
    setRpcUrl(clean);
    try {
      localStorage.setItem("SECUREOTA_RPC_URL", clean);
    } catch {
      // non-fatal
    }
    setStatusMessage(`RPC endpoint set: ${clean}`);
  }, []);

  // Phone-reachable RPC (the HTTPS tunnel). Separate from rpcUrl: the desktop
  // reads its own node over localhost, but the phone cannot — 127.0.0.1 on a
  // phone is the phone itself, and MetaMask Mobile rejects plain http.
  const [phoneRpcUrl, setPhoneRpcUrl] = useState<string>(() => {
    try {
      const stored = (localStorage.getItem("SECUREOTA_PHONE_RPC_URL") ?? "").trim();
      if (isPhoneRpcUrl(stored)) return stored;
    } catch {
      // ignore — unset below
    }
    return "";
  });

  const updatePhoneRpcUrl = useCallback((url: string) => {
    const clean = (url || "").trim().replace(/\/+$/, "");
    if (!isPhoneRpcUrl(clean)) {
      setStatusMessage(
        `Invalid phone RPC rejected: "${url}" — MetaMask Mobile needs an https:// URL (the cloudflared tunnel); keeping current value.`
      );
      return;
    }
    setPhoneRpcUrl(clean);
    try {
      localStorage.setItem("SECUREOTA_PHONE_RPC_URL", clean);
    } catch {
      // non-fatal
    }
    setStatusMessage(`Phone RPC set: ${clean}`);
  }, []);

  // demo-up.bat exports the fresh tunnel URL on every run; it wins over a
  // stored one because quick-tunnel hostnames rotate per run.
  useEffect(() => {
    const bridge = getDesktopBridge();
    if (!bridge?.getPhoneRpcUrl) return;
    void bridge
      .getPhoneRpcUrl()
      .then((url) => {
        if (!url || !isPhoneRpcUrl(url)) return;
        setPhoneRpcUrl(url);
        try {
          localStorage.setItem("SECUREOTA_PHONE_RPC_URL", url);
        } catch {
          // non-fatal
        }
      })
      .catch(() => {
        // older desktop build without the channel — manual entry still works
      });
  }, []);

  // Check if connected account is one of the Hardhat authorized developers
  const isAuthorized = address
    ? HARDHAT_AUTHORIZED_DEVS.some(
        (dev: string) => dev.toLowerCase() === address.toLowerCase()
      )
    : false;

  // Save contract address changes to localStorage — P0-3 strict validation:
  // malformed/empty input is loudly rejected and never persisted.
  const updateContractAddress = useCallback((addr: string) => {
    const clean = (addr || "").trim();
    if (!clean || !ethers.isAddress(clean)) {
      setStatusMessage(
        `Invalid contract address rejected: "${addr}" — expected 0x + 40 hex chars; keeping ${contractAddress}.`
      );
      return;
    }
    try {
      const checksummed = ethers.getAddress(clean);
      setContractAddress(checksummed);
      localStorage.setItem("SECUREOTA_CONTRACT_ADDRESS", checksummed);
      setStatusMessage(`Contract address set: ${checksummed}`);
    } catch {
      setStatusMessage(`Invalid contract address rejected: "${addr}" — checksum failed.`);
    }
  }, [contractAddress]);

  // Check for injected Ethereum provider (MetaMask in browser)
  const getInjectedProvider = useCallback(async () => {
    const ethereum = (window as unknown as { ethereum?: ethers.Eip1193Provider }).ethereum;
    if (ethereum) {
      const browserProvider = new ethers.BrowserProvider(ethereum);
      return browserProvider;
    }
    return null;
  }, []);

  // Connect via standard Injected Wallet (MetaMask extension if present)
  const connectInjected = useCallback(async () => {
    setIsConnecting(true);
    setStatusMessage("Connecting to injected wallet...");
    try {
      const provider = await getInjectedProvider();
      if (!provider) {
        throw new Error("No injected Ethereum wallet found (MetaMask). Please open the QR Modal for Mobile WalletConnect.");
      }
      const accounts = await provider.send("eth_requestAccounts", []);
      if (accounts && accounts.length > 0) {
        const net = await provider.getNetwork();
        setAddress(accounts[0]);
        setChainId(Number(net.chainId));
        setIsConnected(true);
        setStatusMessage(`Connected: ${truncateAddress(accounts[0])}`);
        return accounts[0];
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Injected wallet connection failed";
      setStatusMessage(`Error: ${msg}`);
      throw err;
    } finally {
      setIsConnecting(false);
    }
  }, [getInjectedProvider]);

  // Connect via Reown AppKit (MetaMask Mobile QR code / WalletConnect)
  const openWalletModal = useCallback(async () => {
    setIsConnecting(true);
    setStatusMessage("Opening WalletConnect QR Modal...");
    try {
      const modal = getAppKit();
      if (modal) {
        let before: string | null = null;
        try {
          before =
            (modal.getAccount() as unknown as { address?: string } | undefined)?.address ??
            null;
        } catch {
          before = null;
        }
        await modal.open();
        // Stall watchdog: approval happens on the phone; if nothing connects
        // within 90s, say exactly what to check instead of spinning forever.
        window.setTimeout(() => {
          let now: string | null = null;
          try {
            now =
              (modal.getAccount() as unknown as { address?: string } | undefined)
                ?.address ?? null;
          } catch {
            now = null;
          }
          if (!now || now === before) {
            setStatusMessage(
              "Still waiting for phone approval (90s) — check MetaMask for the connect prompt and that the phone has internet (WalletConnect relay), then re-scan. Dev signers need no phone at all."
            );
          }
        }, 90000);
        // Subscribe to state — AppKit may report CAIP strings, so normalize;
        // garbage never becomes chain state (see parseChainId).
        modalStateUnsub?.();
        modalStateUnsub = modal.subscribeState((state: { selectedNetworkId?: string | number }) => {
          const parsed = parseChainId(state.selectedNetworkId);
          if (parsed !== null) setChainId(parsed);
        });
      } else {
        // Fallback: open our custom high-visibility QR Code overlay modal
        setIsQrModalOpen(true);
      }
    } catch (err) {
      // Never fail silently: the overlay stays open as the error surface
      // (its QR tab renders the failure + retry instead of any QR code).
      const msg = err instanceof Error ? err.message : "Unknown error starting WalletConnect";
      setStatusMessage(`WalletConnect failed: ${msg} — retry from the QR tab or use a Dev signer.`);
      setIsQrModalOpen(true);
    } finally {
      setIsConnecting(false);
    }
  }, []);

  // Open custom QR Code modal with connection details
  const openCustomQrModal = useCallback((uri?: string) => {
    if (uri) setConnectionUri(uri);
    setIsQrModalOpen(true);
  }, []);

  const closeCustomQrModal = useCallback(() => {
    setIsQrModalOpen(false);
  }, []);

  // Connect with a specific Hardhat test private key or account address directly (for rapid testing)
  // P0-4: dev-only — no-op with a loud status in production builds.
  const connectDevAccount = useCallback(async (devIndex = 0) => {
    const isDevBuild =
      (import.meta as unknown as { env: Record<string, string | boolean | undefined> }).env
        ?.DEV === true;
    if (!isDevBuild) {
      setStatusMessage("Dev signers are disabled in production — connect an external wallet.");
      throw new Error("Dev signers are disabled in production builds.");
    }
    const devAddr = HARDHAT_AUTHORIZED_DEVS[devIndex] || HARDHAT_AUTHORIZED_DEVS[0];
    setAddress(devAddr);
    setChainId(31337);
    setIsConnected(true);
    setStatusMessage(`Connected Dev #${devIndex + 1}: ${truncateAddress(devAddr)}`);
  }, []);

  // Verified session identity (challenge-response): the connected address is
  // a CLAIM until the operator signs a login challenge with the matching key
  // AND the contract confirms authorizedDevelopers. Typing an address alone
  // never verifies — possession + on-chain authorization, both required.
  // Cleared on disconnect, account/contract/RPC change (re-verify after any).
  const [verifiedAddress, setVerifiedAddress] = useState<string | null>(null);
  useEffect(() => {
    setVerifiedAddress(null);
  }, [address, contractAddress, rpcUrl]);

  const disconnect = useCallback(() => {
    setAddress(null);
    setChainId(null);
    setIsConnected(false);
    setVerifiedAddress(null);
    lastChainEnsureAddr = null;
    setStatusMessage("Wallet disconnected");
    const modal = getAppKit();
    if (modal) {
      try {
        void modal.disconnect();
      } catch {
        // ignore
      }
    }
  }, []);

  const [signerOrigin, setSignerOrigin] = useState<SignerOrigin | null>(null);

  // Phone wallets (MetaMask Mobile) cannot reach our node until chain 31337
  // exists IN the phone with a reachable RPC. After an AppKit session
  // connects, steer the phone onto the right chain: if the session already
  // approved 31337 the provider switches locally (the phone has the network);
  // otherwise the switch goes to the phone, and when the wallet reports the
  // chain unknown (EIP-4902) it is added with the phone RPC (HTTPS tunnel —
  // never the desktop's localhost RPC, which on a phone points at itself).
  const ensurePhoneChain = useCallback(async () => {
    if (!address || lastChainEnsureAddr === address) return;
    let wp: ethers.Eip1193Provider | null = null;
    try {
      wp =
        (getAppKit()?.getWalletProvider() as unknown as
          | ethers.Eip1193Provider
          | undefined) ?? null;
    } catch {
      return;
    }
    if (!wp) return;
    lastChainEnsureAddr = address;
    const hexChainId = `0x${HARDHAT_CHAIN_ID.toString(16)}`;
    const approvedAccounts = asWcInternals(wp)?.session?.namespaces?.eip155?.accounts ?? [];
    const alreadyApproved = approvedAccounts.some((a) =>
      a.startsWith(`eip155:${HARDHAT_CHAIN_ID}:`)
    );
    try {
      await wp.request({ method: "wallet_switchEthereumChain", params: [{ chainId: hexChainId }] });
      setStatusMessage(
        alreadyApproved
          ? "Phone session approved chain 31337 — signing requests target Hardhat Localhost."
          : "Phone wallet switched to Hardhat Localhost (chain 31337)."
      );
    } catch (switchErr: unknown) {
      const code = (switchErr as { code?: number })?.code;
      const msg = switchErr instanceof Error ? switchErr.message : "";
      const unknownChain =
        code === 4902 || /unknown|unrecognized|not (added|found|available)/i.test(msg);
      if (!unknownChain) {
        setStatusMessage(
          `Phone connected but chain switch was refused (${msg || "no reason given"}) — switch to chain 31337 manually.`
        );
        return;
      }
      if (!phoneRpcUrl) {
        setStatusMessage(
          "Phone has no chain 31337 and no phone RPC is set — enter the https://…trycloudflare.com tunnel URL under Contract Config → Phone RPC, then disconnect and re-scan."
        );
        lastChainEnsureAddr = null;
        return;
      }
      try {
        await wp.request({
          method: "wallet_addEthereumChain",
          params: [
            {
              chainId: hexChainId,
              chainName: "Hardhat Localhost",
              nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
              rpcUrls: [phoneRpcUrl],
            },
          ],
        });
        setStatusMessage(
          `Added Hardhat Localhost (31337) to the phone with RPC ${phoneRpcUrl} — approve the switch prompt in MetaMask.`
        );
      } catch (addErr: unknown) {
        const addMsg = addErr instanceof Error ? addErr.message : "chain add refused";
        setStatusMessage(
          `Phone connected but chain 31337 could not be added (${addMsg}). Add it manually in MetaMask: chain 31337, RPC ${phoneRpcUrl}.`
        );
      }
    }
  }, [address, phoneRpcUrl]);

  // Chain-verified authorization (real-life): the local HARDHAT_AUTHORIZED_DEVS
  // list is a display hint only — the contract's authorizedDevelopers mapping
  // is truth. Explicit false warns loudly; null means unknown (no contract /
  // unreachable node) and never false-alarms.
  const [chainAuthorized, setChainAuthorized] = useState<boolean | null>(null);
  useEffect(() => {
    if (!address || !contractAddress || !ethers.isAddress(contractAddress)) {
      setChainAuthorized(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const provider = new ethers.JsonRpcProvider(rpcUrl);
        if ((await provider.getCode(contractAddress)) === "0x") return;
        const contract = new ethers.Contract(contractAddress, DELTA_OTA_ABI, provider);
        const ok = (await contract.authorizedDevelopers(address)) as boolean;
        if (cancelled) return;
        setChainAuthorized(ok);
        if (!ok) {
          setStatusMessage(
            `Connected ${truncateAddress(address)} is NOT an authorized dev on this contract — propose/approve will revert. Switch wallet.`
          );
        }
      } catch {
        if (!cancelled) setChainAuthorized(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [address, contractAddress, rpcUrl]);

  const normalizeAddress = (addr: string | undefined): string | null => {
    if (!addr) return null;
    // AppKit may report CAIP `eip155:<chain>:<0x...>` — keep the hex tail.
    const parts = addr.split(":");
    const tail = parts[parts.length - 1];
    return tail || null;
  };

  // Keep UI identity in sync with the real AppKit session (QR-paired phone
  // included). Fires on connect, account switch, and disconnect/expiry.
  useEffect(() => {
    const modal = getAppKit();
    if (!modal) return;
    const sync = (s: { address?: string; isConnected?: boolean }) => {
      const addr = normalizeAddress(s.address);
      setAddress(addr);
      setIsConnected(s.isConnected === true && addr !== null);
      if (addr) {
        setStatusMessage(`Connected: ${truncateAddress(addr)}`);
        // Steer the freshly paired phone onto chain 31337 (switch, or add
        // with the configured RPC when unknown) — otherwise it stalls.
        void ensurePhoneChain();
        // Chain the signer will actually use: the provider's default chain
        // (answered locally, no phone round-trip) — the same value getSigner
        // checks, so the gates and the signer cannot disagree.
        void (async () => {
          try {
            const wp = modal?.getWalletProvider() as unknown as
              ethers.Eip1193Provider | undefined;
            if (!wp) return;
            const provider = new ethers.BrowserProvider(wp);
            const net = await Promise.race([
              provider.getNetwork(),
              new Promise<never>((_, reject) =>
                window.setTimeout(() => reject(new Error("chain probe timeout")), 5000)
              ),
            ]);
            setChainId(Number(net.chainId));
          } catch {
            // leave prior chain state; per-tx checks still guard broadcasts
          }
        })();
      } else if (s.isConnected === false) {
        lastChainEnsureAddr = null;
        setStatusMessage("Wallet disconnected (session ended — re-scan to reconnect)");
      }
    };
    // Seed from a possibly restored WalletConnect session.
    try {
      const current = modal.getAccount() as unknown as
        { address?: string; isConnected?: boolean } | undefined;
      if (current) sync(current);
    } catch {
      // ignore — subscription below covers live changes
    }
    const unsub = modal.subscribeAccount(sync);
    return unsub;
    // Re-subscribes when the steering callback refreshes (address/RPC
    // change) so sync always steers with live values; seed sets are
    // idempotent so this never loops.
  }, [ensurePhoneChain]);

  // Boot validation (once): a restored WC session must prove liveness. The
  // provider answers eth_chainId/eth_accounts locally, so only a relay ping
  // reaches the phone — a session whose phone never answers is forgotten
  // instead of trusted (re-scan to reconnect).
  useEffect(() => {
    const modal = getAppKit();
    if (!modal) return;
    void (async () => {
      try {
        const cur = modal.getAccount() as unknown as
          { address?: string; isConnected?: boolean } | undefined;
        if (!cur?.isConnected || !cur?.address) return;
        const wc = asWcInternals(modal.getWalletProvider());
        // dev/injected sessions validate through their own flows
        if (!wc?.client || !wc.session?.topic) return;
        await raceTimeout(wc.client.ping({ topic: wc.session.topic }), 15000, "stale session");
      } catch {
        try {
          await modal.disconnect();
        } catch {
          // ignore — state reset below is the guarantee, relay drop is bonus
        }
        lastChainEnsureAddr = null;
        setAddress(null);
        setChainId(null);
        setIsConnected(false);
        setStatusMessage(
          "Restored phone session did not answer (15s ping) — forgotten. Open MetaMask on the phone and re-scan."
        );
      }
    })();
  }, []);

  // Best-effort forget on close (pagehide covers desktop + mobile; browsers
  // may skip async work here, so boot validation above is the guarantee).
  useEffect(() => {
    const forget = () => {
      try {
        const modal = getAppKit();
        void modal?.disconnect?.();
      } catch {
        // ignore — closing anyway
      }
      setAddress(null);
      setChainId(null);
      setIsConnected(false);
    };
    window.addEventListener("pagehide", forget);
    window.addEventListener("beforeunload", forget);
    return () => {
      window.removeEventListener("pagehide", forget);
      window.removeEventListener("beforeunload", forget);
    };
  }, []);

  // Resolve the EIP-1193 provider of an AppKit-paired wallet (MetaMask
  // Mobile via QR). Null when no wallet session is active.
  const getAppKitWalletProvider = (): ethers.Eip1193Provider | null => {
    try {
      const modal = getAppKit();
      const wp = modal?.getWalletProvider() as unknown as
        ethers.Eip1193Provider | undefined;
      return wp ?? null;
    } catch {
      return null;
    }
  };

  // Signer priority (extension-first): browser extension first (same-machine,
  // localhost RPC, no relay or tunnel involved), phone wallet second,
  // Hardhat unlocked accounts last in dev builds only (labeled dev fallback).
  // Throws a clear error when the active wallet sits on the wrong chain.
  const getSigner = useCallback(async (): Promise<{
    signer: ethers.Signer;
    origin: SignerOrigin;
  }> => {
    const injected = await getInjectedProvider();
    if (injected) {
      const net = await injected.getNetwork();
      if (Number(net.chainId) !== HARDHAT_CHAIN_ID) {
        throw new Error(
          `Injected wallet is on chain ${net.chainId} — switch to Hardhat Localhost (chain ${HARDHAT_CHAIN_ID}).`
        );
      }
      setSignerOrigin("injected");
      return { signer: await injected.getSigner(), origin: "injected" as const };
    }
    const wc = getAppKitWalletProvider();
    if (wc) {
      const provider = new ethers.BrowserProvider(wc);
      const net = await provider.getNetwork();
      if (Number(net.chainId) !== HARDHAT_CHAIN_ID) {
        throw new Error(
          `Wallet is on chain ${net.chainId} — switch MetaMask to Hardhat Localhost (chain ${HARDHAT_CHAIN_ID}).`
        );
      }
      setSignerOrigin("wallet");
      return { signer: await provider.getSigner(), origin: "wallet" as const };
    }
    // P0-4: dev-node fallback exists ONLY in dev builds. Production
    // (packaged app is always a prod build) is external-wallets-only —
    // no silent node signing, callers get a loud error instead.
    const isDevBuild =
      (import.meta as unknown as { env: Record<string, string | boolean | undefined> }).env
        ?.DEV === true;
    if (!isDevBuild) {
      throw new Error(
        "No wallet session — connect via Reown QR or a MetaMask extension on Hardhat Localhost (dev-node fallback is disabled in production)."
      );
    }
    // In dev/desktop headless mode without any wallet, sign with the local
    // Hardhat node's unlocked accounts (configurable LAN RPC). No phone
    // prompt happens on this path — callers must label it honestly.
    const jsonRpcProvider = new ethers.JsonRpcProvider(rpcUrl);
    setSignerOrigin("dev-node");
    if (address) {
      return { signer: await jsonRpcProvider.getSigner(address), origin: "dev-node" as const };
    }
    // Default to first account on the node
    return { signer: await jsonRpcProvider.getSigner(0), origin: "dev-node" as const };
  }, [address, getInjectedProvider, rpcUrl]);

  /**
   * Prove ownership of the connected session address: sign a fresh login
   * challenge, recover the signer, require equality with the session claim,
   * then require contract authorization. Resolves the checksummed address;
   * throws operator-worded errors otherwise (never verifies silently).
   * Defined after getSigner (declaration order matters to the compiler).
   */
  const verifyIdentity = useCallback(async (): Promise<string> => {
    if (!address) {
      throw new Error("No wallet session — connect first, then verify ownership.");
    }
    if (!contractAddress || !ethers.isAddress(contractAddress)) {
      throw new Error("No contract configured — set the deployed address in Contract Config first.");
    }
    const { signer, origin } = await raceTimeout(
      getSigner(),
      60000,
      "Timed out reaching a signer — no wallet answered (app closed? session dead?). Reconnect and retry."
    );
    // Stamp the verified truth: the signer's live network overwrites any
    // gossip the state subscription carried. Gate and signer can no longer
    // disagree after a successful verification.
    try {
      const prov = signer.provider as unknown as ethers.Provider | null;
      if (prov) {
        const net = await raceTimeout(prov.getNetwork(), 5000, "reading wallet network");
        setChainId(Number(net.chainId));
      }
    } catch {
      // non-fatal: per-tx chain checks still guard every broadcast
    }
    const nonce = ethers.hexlify(ethers.randomBytes(8));
    const message = `DeltaOTA console login\ncontract: ${contractAddress}\nnonce: ${nonce}`;
    setStatusMessage(
      origin === "dev-node"
        ? "Signing login challenge via DEV SIGNER (no phone prompt)..."
        : "Signing login challenge — approve in your wallet (60s timeout)..."
    );
    const signature = await raceTimeout(
      signer.signMessage(message),
      60000,
      "Timed out waiting for the login signature — the challenge was not approved (prompt ignored? wrong app?). No session was verified. Retry."
    );
    const recovered = ethers.verifyMessage(message, signature);
    if (recovered.toLowerCase() !== address.toLowerCase()) {
      throw new Error(
        `Challenge signed by ${truncateAddress(recovered)} — does not match connected ${truncateAddress(address)}. Session NOT verified (wrong account signed?).`
      );
    }
    const provider = new ethers.JsonRpcProvider(rpcUrl);
    if ((await provider.getCode(contractAddress)) === "0x") {
      throw new Error(
        `No contract code at ${contractAddress} on ${rpcUrl} — deploy first. Session NOT verified.`
      );
    }
    const contract = new ethers.Contract(contractAddress, DELTA_OTA_ABI, provider);
    if (!(await contract.authorizedDevelopers(recovered))) {
      throw new Error(
        `${truncateAddress(recovered)} proved key ownership but is NOT an authorized dev on this contract — console stays read-only.`
      );
    }
    const checksummed = ethers.getAddress(recovered);
    setVerifiedAddress(checksummed);
    setStatusMessage(`Identity verified: ${truncateAddress(checksummed)} (authorized dev, challenge-signed).`);
    return checksummed;
  }, [address, contractAddress, rpcUrl, getSigner]);

  /**
   * Payload 1: proposeRelease(bytes32 version, bytes32 goldenHash, string ipfsUrl)
   */
  const proposeRelease = useCallback(
    async (
      version: string,
      goldenHash: string,
      ipfsUrl: string
    ): Promise<ContractTransactionReceipt> => {
      const { signer, origin } = await getSigner();
      const contract = new ethers.Contract(contractAddress, DELTA_OTA_ABI, signer);

      const versionBytes32 = formatVersionBytes32(version);
      const hashBytes32 = formatGoldenHashBytes32(goldenHash);

      setStatusMessage(`Submitting proposeRelease(${version})...`);
      const tx = await contract.proposeRelease(versionBytes32, hashBytes32, ipfsUrl);
      const receipt = await tx.wait();

      setStatusMessage(`Release proposed on-chain! Block #${receipt.blockNumber}`);
      return {
        hash: receipt.hash,
        blockNumber: receipt.blockNumber,
        from: receipt.from,
        origin,
      };
    },
    [contractAddress, getSigner]
  );

  /**
   * Payload 2: approveRelease(bytes32 version)
   */
  const approveRelease = useCallback(
    async (version: string): Promise<ContractTransactionReceipt> => {
      const { signer, origin } = await getSigner();
      const contract = new ethers.Contract(contractAddress, DELTA_OTA_ABI, signer);

      const versionBytes32 = formatVersionBytes32(version);

      setStatusMessage(`Approving release ${version}...`);
      const tx = await contract.approveRelease(versionBytes32);
      const receipt = await tx.wait();

      setStatusMessage(`Approved ${version} on-chain! Block #${receipt.blockNumber}`);
      return {
        hash: receipt.hash,
        blockNumber: receipt.blockNumber,
        from: receipt.from,
        origin,
      };
    },
    [contractAddress, getSigner]
  );

  /**
   * Payload 3: revokeRelease(bytes32 version) - Emergency Kill Switch
   */
  const revokeRelease = useCallback(
    async (version: string): Promise<ContractTransactionReceipt> => {
      const { signer, origin } = await getSigner();
      const contract = new ethers.Contract(contractAddress, DELTA_OTA_ABI, signer);

      const versionBytes32 = formatVersionBytes32(version);

      setStatusMessage(`Revoking release ${version} via Kill Switch...`);
      const tx = await contract.revokeRelease(versionBytes32);
      const receipt = await tx.wait();

      setStatusMessage(`Revoked ${version} on-chain! Block #${receipt.blockNumber}`);
      return {
        hash: receipt.hash,
        blockNumber: receipt.blockNumber,
        from: receipt.from,
        origin,
      };
    },
    [contractAddress, getSigner]
  );

  /**
   * Query contract state for a version — chain-as-truth read path (P0-2).
   * Returns a structured record (never raw ethers tuple) or null when the
   * node is unreachable. Callers merge this into the local ledger cache.
   */
  const fetchRelease = useCallback(
    async (version: string): Promise<OnChainReleaseRecord | null> => {
      // Empty/malformed address: nothing to query (empty default until the
      // operator configures a deployment). Return quietly — no ENS noise.
      if (!contractAddress || !ethers.isAddress(contractAddress)) return null;
      try {
        const jsonRpcProvider = new ethers.JsonRpcProvider(rpcUrl);
        const contract = new ethers.Contract(contractAddress, DELTA_OTA_ABI, jsonRpcProvider);
        const versionBytes32 = formatVersionBytes32(version);
        const raw = await contract.getRelease(versionBytes32);
        // Ethers v6 returns array-like + named props; handle both shapes.
        const goldenHash: string =
          (raw?.goldenHash as string | undefined) ?? (raw?.[1] as string | undefined) ?? "";
        const ipfsUrl: string =
          (raw?.ipfsUrl as string | undefined) ?? (raw?.[2] as string | undefined) ?? "";
        const approvalRaw = (raw?.approvalCount as unknown) ?? raw?.[3] ?? 0;
        const approvalCount =
          typeof approvalRaw === "bigint" ? Number(approvalRaw) : Number(approvalRaw as number);
        const isLive: boolean =
          (raw?.isLive as boolean | undefined) ?? (raw?.[4] as boolean | undefined) ?? false;
        const isRevoked: boolean =
          (raw?.isRevoked as boolean | undefined) ?? (raw?.[5] as boolean | undefined) ?? false;
        return {
          version,
          goldenHash:
            goldenHash === ethers.ZeroHash ? "" : goldenHash,
          ipfsUrl,
          approvalCount: Number.isFinite(approvalCount) ? approvalCount : 0,
          isLive,
          isRevoked,
        };
      } catch (err) {
        console.warn("Could not query contract release:", err);
        return null;
      }
    },
    [contractAddress, rpcUrl]
  );

  /**
   * Who proposed a version — read from the on-chain ReleaseProposed event, so
   * it survives app restarts. Lowercased address, or null when the version
   * was never proposed or the node is unreachable. version is not an indexed
   * event field, so all ReleaseProposed logs are fetched and matched here.
   */
  const fetchProposer = useCallback(
    async (version: string): Promise<string | null> => {
      if (!contractAddress || !ethers.isAddress(contractAddress)) return null;
      try {
        const jsonRpcProvider = new ethers.JsonRpcProvider(rpcUrl);
        const contract = new ethers.Contract(contractAddress, DELTA_OTA_ABI, jsonRpcProvider);
        const wanted = formatVersionBytes32(version).toLowerCase();
        const logs = await contract.queryFilter(contract.filters.ReleaseProposed(), 0);
        for (const log of logs) {
          const args = (log as ethers.EventLog).args;
          if (args && String(args.version).toLowerCase() === wanted) {
            return String(args.proposer).toLowerCase();
          }
        }
        return null;
      } catch (err) {
        console.warn("Could not query release proposer:", err);
        return null;
      }
    },
    [contractAddress, rpcUrl]
  );

  return {
    address,
    chainId,
    isConnected,
    isConnecting,
    isAuthorized,
    connectionUri,
    isQrModalOpen,
    contractAddress,
    rpcUrl,
    statusMessage,
    signerOrigin,
    chainAuthorized,
    verifiedAddress,
    isVerified: verifiedAddress !== null,
    verifyIdentity,
    updateContractAddress,
    updateRpcUrl,
    phoneRpcUrl,
    updatePhoneRpcUrl,
    connectInjected,
    openWalletModal,
    openCustomQrModal,
    closeCustomQrModal,
    connectDevAccount,
    disconnect,
    proposeRelease,
    approveRelease,
    revokeRelease,
    fetchRelease,
    fetchProposer,
  };
}
