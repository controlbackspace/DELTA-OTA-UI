import { ethers } from "ethers";

/**
 * Encodes a version string (e.g. "v1.1") into a bytes32 hex string.
 * DeltaOTA contract stores version as bytes32: releases[version]
 */
export function formatVersionBytes32(version: string): string {
  // If already 0x hex format of length 66, return as is
  if (version.startsWith("0x") && version.length === 66) {
    return version;
  }
  // Trim spaces and normalize
  const clean = version.trim();
  return ethers.encodeBytes32String(clean);
}

/**
 * Decodes a bytes32 hex string back into human readable version (e.g. "v1.1")
 */
export function parseVersionBytes32(bytes32Str: string): string {
  try {
    return ethers.decodeBytes32String(bytes32Str);
  } catch {
    return bytes32Str;
  }
}

/**
 * Normalizes a SHA-256 golden hash into a strict 32-byte 0x-prefixed hex string (66 chars).
 */
export function formatGoldenHashBytes32(hash: string): string {
  let clean = hash.trim();
  if (!clean.startsWith("0x")) {
    clean = `0x${clean}`;
  }
  if (clean.length === 66) {
    return clean;
  }
  // If truncated or formatted as simulation dummy (e.g. "0x8e5b0d3c...8e0f"), zero-pad or hash
  if (clean.length < 66) {
    return ethers.zeroPadValue(clean, 32);
  }
  return clean.slice(0, 66);
}

/**
 * Validates whether an Ethereum address is well-formed
 */
export function isValidEthereumAddress(address: string): boolean {
  return ethers.isAddress(address);
}

/**
 * Shortens an address for display (0x1234...5678)
 */
export function truncateAddress(address: string, chars = 4): string {
  if (!address) return "";
  return `${address.slice(0, chars + 2)}...${address.slice(-chars)}`;
}
