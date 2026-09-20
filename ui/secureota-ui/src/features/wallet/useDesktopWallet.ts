import { useState, useCallback } from "react";
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

// WalletConnect Project ID for Reown AppKit
// For local simulation, we provide a valid format project ID or read from env
export const REOWN_PROJECT_ID =
  (import.meta as unknown as { env: Record<string, string> }).env?.VITE_REOWN_PROJECT_ID ||
  "c585c542c3886b61a38fb9279093e0e7";

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

export interface ContractTransactionReceipt {
  hash: string;
  blockNumber: number;
  from: string;
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
      console.warn("AppKit modal open failed, falling back to custom QR overlay:", err);
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

  // Get active ethers Signer (via injected provider or local JSON-RPC provider)
  const getSigner = useCallback(async (): Promise<ethers.Signer> => {
    const injected = await getInjectedProvider();
    if (injected) {
      return await injected.getSigner();
    }
    // In desktop or headless mode without injected window.ethereum,
    // connect to local Hardhat JSON-RPC node directly (http://127.0.0.1:8545)
    const jsonRpcProvider = new ethers.JsonRpcProvider("http://127.0.0.1:8545");
    if (address) {
      return await jsonRpcProvider.getSigner(address);
    }
    // Default to first account on the node
    return await jsonRpcProvider.getSigner(0);
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
      const signer = await getSigner();
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
      };
    },
    [contractAddress, getSigner]
  );

  /**
   * Payload 2: approveRelease(bytes32 version)
   */
  const approveRelease = useCallback(
    async (version: string): Promise<ContractTransactionReceipt> => {
      const signer = await getSigner();
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
      };
    },
    [contractAddress, getSigner]
  );

  /**
   * Payload 3: revokeRelease(bytes32 version) - Emergency Kill Switch
   */
  const revokeRelease = useCallback(
    async (version: string): Promise<ContractTransactionReceipt> => {
      const signer = await getSigner();
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
