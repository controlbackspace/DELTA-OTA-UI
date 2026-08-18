from web3 import Web3
import asyncio
import json
import os

class BlockchainPoller:
    def __init__(self):
        #Assigning the local Hardhat HTTP endpoint string (overridable via env var)
        self.rpc_url = os.getenv('DELTA_RPC_URL', 'http://127.0.0.1:8545')

        #Assigning the contract address string (overridable via env var)
        self.contract_address = os.getenv('DELTA_CONTRACT_ADDRESS', "0x445bd590A01fe6709d4f13A8F579c1e4846921db")

        #Pasting the standard Mock ABI JSON array we defined in the meeting
        self.CONTRACT_ABI = [{

            "inputs": [
                    { "internalType": "bytes32", "name": "version", "type": "bytes32" },
                    { "internalType": "bytes32", "name": "goldenHash", "type": "bytes32" },
                    { "internalType": "string", "name": "ipfsUrl", "type": "string" }
                    ],
                    "name": "proposeRelease",
                    "outputs": [],
                    "stateMutability": "nonpayable",
                    "type": "function"
                },
        {
            "inputs": [
                { "internalType": "bytes32", "name": "version", "type": "bytes32" }
                ],
                    "name": "approveRelease",
                    "outputs": [],
                    "stateMutability": "nonpayable",
                    "type": "function"
        },
        {
            "inputs": [
                { "internalType": "bytes32", "name": "version", "type": "bytes32" }
                ],
                    "name": "revokeRelease",
                    "outputs": [],
                    "stateMutability": "nonpayable",
                    "type": "function"
        },
        {
            "inputs": [
                { "internalType": "bytes32", "name": "version", "type": "bytes32" }
                ],
                    "name": "getRelease",
                    "outputs": [
                {
                    "components": [
                        { "internalType": "bytes32", "name": "version", "type": "bytes32" },
                        { "internalType": "bytes32", "name": "goldenHash", "type": "bytes32" },
                        { "internalType": "string", "name": "ipfsUrl", "type": "string" },
                        { "internalType": "uint8", "name": "approvalCount", "type": "uint8" },
                        { "internalType": "bool", "name": "isLive", "type": "bool" },
                        { "internalType": "bool", "name": "isRevoked", "type": "bool" }
                        ],
                        "internalType": "struct DeltaOTA.FirmwareRelease",
                        "name": "",
                        "type": "tuple"
                }
                    ],
                    "stateMutability": "view",
                    "type": "function"
        }
        ]
        
        # Created the Web3 HTTPProvider using self.rpc_url
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))

        # Wrote an if/else block to check self.w3.is_connected()
        # Print a success message to the terminal if True, or a failure warning if False.
        
        if self.w3.is_connected():
            print("Success!")
        else:
            print("Failure Warning!")

        if self.w3 and self.w3.is_connected():
            self.contract = self.w3.eth.contract(
                address=self.contract_address, 
                abi=self.CONTRACT_ABI
            )
        else:
            self.contract = None

    async def fetch_firmware_release(self, version_tag: str):
        print(f"\n[Network] Polling ledger for firmware version: {version_tag}...")
        
        # Security Check: Ensure we are connected before polling
        if not self.contract:
            print("[Error] Gateway is not connected to the blockchain. Aborting poll.")
            return None

        try:
            # 1. Format the Input: Solidity expects exactly 32 bytes
            encoded_version = version_tag.encode('utf-8').ljust(32, b'\0')

            # 2. Execute the Call: Read the state from the local node
            # We use asyncio.to_thread because web3.py .call() is synchronous and would block the CoAP server
            result = await asyncio.to_thread(
                self.contract.functions.getRelease(encoded_version).call
            )

            # 3. Unpack the Tuple: Map the Solidity struct to Python variables
            version_bytes, golden_hash_bytes, ipfs_url, approval_count, is_live, is_revoked = result

            live_firmware_release = {
                "version": version_bytes.replace(b'\0', b'').decode('utf-8'),
                "goldenHash": golden_hash_bytes.hex(),
                "ipfsUrl": ipfs_url,
                "approvalCount": approval_count,
                "isLive": is_live,
                "isRevoked": is_revoked
            }

            print(f"[Ledger] Successfully retrieved state for {version_tag}: Live={is_live}, Revoked={is_revoked}")
            return live_firmware_release

        except Exception as e:
            print(f"[Ledger Error] Failed to fetch release state: {e}")
            return None

# Quick test execution block
if __name__ == "__main__":
    print("Initializing Edge Gateway Poller...")
    poller = BlockchainPoller()