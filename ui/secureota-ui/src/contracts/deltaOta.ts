/**
 * DeltaOTA Smart Contract ABI and Hardhat Localhost Configuration
 */

export const DELTA_OTA_ABI = [
  "function proposeRelease(bytes32 version, bytes32 goldenHash, string calldata ipfsUrl) external",
  "function approveRelease(bytes32 version) external",
  "function revokeRelease(bytes32 version) external",
  "function getRelease(bytes32 version) external view returns (tuple(bytes32 version, bytes32 goldenHash, string ipfsUrl, uint8 approvalCount, bool isLive, bool isRevoked))",
  "function authorizedDevelopers(address) external view returns (bool)",
  "function hasSigned(bytes32, address) external view returns (bool)",
  "function thresholdM() external view returns (uint8)",
  "function totalDevelopersN() external view returns (uint8)",
  "event ReleaseProposed(bytes32 version, bytes32 goldenHash, string ipfsUrl, address indexed proposer)",
  "event ReleaseApproved(bytes32 version, address indexed approver, uint8 currentApprovals)",
  "event ReleasePromotedToLive(bytes32 version, bytes32 goldenHash, string ipfsUrl)",
  "event ReleaseRevoked(bytes32 version, address indexed revoker)"
] as const;

// Default contract address when deployed via blockchain/scripts/deploy.js
// Dev can override this in localStorage or via the UI settings modal
export const DEFAULT_CONTRACT_ADDRESS = "0x5FbDB2315678afecb367f032d93F642f64180aa3";

// Standard Hardhat Localhost Network Config
export const HARDHAT_LOCAL_CHAIN = {
  id: 31337,
  name: "Hardhat Localhost",
  nativeCurrency: { name: "Ether", symbol: "ETH", decimals: 18 },
  rpcUrls: {
    default: { http: ["http://127.0.0.1:8545"] },
  },
};

// Hardhat standard authorized developer accounts from deploy.js:
export const HARDHAT_AUTHORIZED_DEVS = [
  "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266", // Dev 1 (deployer / proposer)
  "0x70997970C51812dc3A010C7d01b50e0d17dc79C8", // Dev 2
  "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC", // Dev 3
];
