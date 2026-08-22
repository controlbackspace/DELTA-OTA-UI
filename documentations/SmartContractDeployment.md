# DeltaOTA Smart Contract: Run and Deploy

This guide explains how to compile and deploy the DeltaOTA smart contract to a
local Hardhat blockchain for development.

## Project locations

| Item | Location |
| --- | --- |
| Solidity source | `blockchain/contracts/DeltaOTA.sol` |
| Deployment script | `blockchain/scripts/deploy.js` |
| Hardhat configuration | `blockchain/hardhat.config.js` |
| Generated artifact | `blockchain/artifacts/contracts/DeltaOTA.sol/DeltaOTA.json` |

## Prerequisites

- Node.js and npm installed
- A PowerShell terminal

From the repository root, install the blockchain dependencies:

```powershell
cd blockchain
npm install
```

## 1. Compile the contract

From the `blockchain` directory, compile the Solidity contract without starting the local blockchain:

```powershell
npx hardhat compile
```

Hardhat writes the ABI and bytecode to:

```text
blockchain/artifacts/contracts/DeltaOTA.sol/DeltaOTA.json
```

## 2. Start the local blockchain

Open a PowerShell terminal in the `blockchain` directory and run:

```powershell
npx hardhat node
```

Keep this terminal open. Hardhat starts a local JSON-RPC node at:

```text
http://127.0.0.1:8545
```

The node prints funded development accounts. The deployment script uses the
first three standard Hardhat accounts as the authorized developers for the
2-of-3 approval contract.

## 3. Deploy DeltaOTA

Open a second PowerShell terminal in the `blockchain` directory and run:

```powershell
npx hardhat run scripts/deploy.js --network localhost
```

The command prints the deployed contract address, for example:

```text
DELTA_OTA CONTRACT ADDRESS: 0x5FbDB2315678afecb367f032d93F642f64180aa3
```

Record the address for local application configuration. The address changes
when the local chain is recreated.

## Verify the deployment

After deployment, confirm that the command completed without an error and that the output includes:

- All three authorized developer addresses
- A `DELTA_OTA CONTRACT ADDRESS` value

The local node must remain running while the deployment command executes.

## Important notes

- Restarting `npx hardhat node` resets the local blockchain and removes the
	previous deployment. Run the deployment command again after a restart.
- The deployment script uses Hardhat test accounts. This setup is for local
	development only and must not be used on a public network.
- Stop the local blockchain with `Ctrl+C` in the Hardhat terminal.

## Troubleshooting

### `Error HH1: You are not inside a Hardhat project`

Change into the blockchain project directory before running Hardhat commands:

```powershell
cd blockchain
npx hardhat compile
```

### Deployment cannot connect to localhost

Start `npx hardhat node` in a separate terminal first, then run the deployment
command with `--network localhost` from the `blockchain` directory.