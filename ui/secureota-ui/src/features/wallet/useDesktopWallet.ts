import { useState, useCallback, useEffect } from "react";
import { ethers } from "ethers";
import { createAppKit } from "@reown/appkit/react";
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

// WalletConnect Project ID for Reown AppKit (public client identifier —
// shipped in the bundle by design, not a secret). Env override wins when set.
export const REOWN_PROJECT_ID =
  (import.meta as unknown as { env: Record<string, string> }).env?.VITE_REOWN_PROJECT_ID ||
  "77a796e27254e03bf5ae9b9aba69b93b";

// Hardhat Localhost chain id (single source of truth for guards below)
export const HARDHAT_CHAIN_ID = 31337;

// Define network definition for AppKit
export const localhostNetwork = {
  id: 31337,
  name: "Hardhat Localhost",
  network: "localhost",
  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
  rpcUrls: {
    default: { http: ["http://127.0.0.1:8545"] },
  },
  testnet: true,
};

// Singleton AppKit instance
let appKitInstance: ReturnType<typeof createAppKit> | null = null;

export function getAppKit() {
  if (typeof window === "undefined") return null;
  if (!appKitInstance) {
    try {
      const ethersAdapter = new EthersAdapter();
      appKitInstance = createAppKit({
        adapters: [ethersAdapter],
        networks: [localhostNetwork],
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
      if (stored && stored.trim() && /^https?:\/\/.+/.test(stored.trim())) {
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
    setRpcUrl(clean);
    try {
      localStorage.setItem("SECUREOTA_RPC_URL", clean);
    } catch {
      // non-fatal
    }
    setStatusMessage(`RPC endpoint set: ${clean}`);
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
        await modal.open();
        // Subscribe to state — AppKit may report CAIP strings, so normalize;
        // garbage never becomes chain state (see parseChainId).
        modal.subscribeState((state: { selectedNetworkId?: string | number }) => {
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
  // Plus boot-time validation: a restored session that cannot answer RPC
  // within 5s is forgotten (covers app-close and dead-node cases — close
  // always reads as disconnected on next open).
  useEffect(() => {
    const modal = getAppKit();
    if (!modal) return;
    const sync = (s: { address?: string; isConnected?: boolean }) => {
      const addr = normalizeAddress(s.address);
      setAddress(addr);
      setIsConnected(s.isConnected === true && addr !== null);
      if (addr) {
        setStatusMessage(`Connected: ${truncateAddress(addr)}`);
        // Authoritative chain: ask the live provider, not AppKit gossip.
        // A stale/wrong state event can never wedge the gates again.
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
    // Boot validation: restored WC sessions must prove liveness. A dead
    // relay/phone/node answers nothing — forget it instead of trusting it.
    void (async () => {
      try {
        const cur = modal.getAccount() as unknown as
          { address?: string; isConnected?: boolean } | undefined;
        if (!cur?.isConnected || !cur?.address) return;
        const wp = modal?.getWalletProvider() as unknown as
          ethers.Eip1193Provider | undefined;
        if (!wp) return; // dev/injected sessions validate through their own flows
        const provider = new ethers.BrowserProvider(wp);
        const net = await Promise.race([
          provider.getNetwork(),
          new Promise<never>((_, reject) =>
            window.setTimeout(() => reject(new Error("stale session")), 5000)
          ),
        ]);
        // A session that answers is also a chain source of truth.
        setChainId(Number(net.chainId));
      } catch {
        try {
          await modal.disconnect();
        } catch {
          // ignore — state reset below is the guarantee, relay drop is bonus
        }
        setAddress(null);
        setChainId(null);
        setIsConnected(false);
        setStatusMessage("Wallet disconnected (session ended — re-scan to reconnect)");
      }
    })();
    const unsub = modal.subscribeAccount(sync);
    return unsub;
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
  };
}
