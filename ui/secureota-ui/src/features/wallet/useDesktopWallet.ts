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

/** Which key actually signed: phone wallet, browser extension, or node fallback. */
export type SignerOrigin = "wallet" | "injected" | "dev-node";

export interface ContractTransactionReceipt {
  hash: string;
  blockNumber: number;
  from: string;
  origin: SignerOrigin;
}

export function useDesktopWallet() {
  const [address, setAddress] = useState<string | null>(null);
  const [chainId, setChainId] = useState<number | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isConnecting, setIsConnecting] = useState<boolean>(false);
  const [connectionUri, setConnectionUri] = useState<string | null>(null);
  const [isQrModalOpen, setIsQrModalOpen] = useState<boolean>(false);
  const [contractAddress, setContractAddress] = useState<string>(() => {
    return localStorage.getItem("SECUREOTA_CONTRACT_ADDRESS") || DEFAULT_CONTRACT_ADDRESS;
  });
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Check if connected account is one of the Hardhat authorized developers
  const isAuthorized = address
    ? HARDHAT_AUTHORIZED_DEVS.some(
        (dev: string) => dev.toLowerCase() === address.toLowerCase()
      )
    : false;

  // Save contract address changes to localStorage
  const updateContractAddress = useCallback((addr: string) => {
    setContractAddress(addr);
    localStorage.setItem("SECUREOTA_CONTRACT_ADDRESS", addr);
  }, []);

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
        // Subscribe to state
        modal.subscribeState((state: { selectedNetworkId?: string | number }) => {
          if (state.selectedNetworkId) {
            setChainId(Number(state.selectedNetworkId));
          }
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
  const connectDevAccount = useCallback(async (devIndex = 0) => {
    const devAddr = HARDHAT_AUTHORIZED_DEVS[devIndex] || HARDHAT_AUTHORIZED_DEVS[0];
    setAddress(devAddr);
    setChainId(31337);
    setIsConnected(true);
    setStatusMessage(`Connected Dev #${devIndex + 1}: ${truncateAddress(devAddr)}`);
  }, []);

  const disconnect = useCallback(() => {
    setAddress(null);
    setChainId(null);
    setIsConnected(false);
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
    const unsub = modal.subscribeAccount(sync);
    return unsub;
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

  // Signer priority: real phone wallet first, browser extension second,
  // Hardhat unlocked accounts last (labeled dev fallback — no phone prompt).
  // Throws a clear error when the active wallet sits on the wrong chain.
  const getSigner = useCallback(async (): Promise<{
    signer: ethers.Signer;
    origin: SignerOrigin;
  }> => {
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
    // In desktop or headless mode without any wallet, sign with the local
    // Hardhat node's unlocked accounts (http://127.0.0.1:8545). No phone
    // prompt happens on this path — callers must label it honestly.
    const jsonRpcProvider = new ethers.JsonRpcProvider("http://127.0.0.1:8545");
    setSignerOrigin("dev-node");
    if (address) {
      return { signer: await jsonRpcProvider.getSigner(address), origin: "dev-node" as const };
    }
    // Default to first account on the node
    return { signer: await jsonRpcProvider.getSigner(0), origin: "dev-node" as const };
  }, [address, getInjectedProvider]);

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
   * Query contract state for a version
   */
  const fetchRelease = useCallback(
    async (version: string) => {
      try {
        const jsonRpcProvider = new ethers.JsonRpcProvider("http://127.0.0.1:8545");
        const contract = new ethers.Contract(contractAddress, DELTA_OTA_ABI, jsonRpcProvider);
        const versionBytes32 = formatVersionBytes32(version);
        return await contract.getRelease(versionBytes32);
      } catch (err) {
        console.warn("Could not query contract release:", err);
        return null;
      }
    },
    [contractAddress]
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
    statusMessage,
    signerOrigin,
    updateContractAddress,
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
