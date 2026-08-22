# DeltaOTA Smart Contract: Run and Deploy

This guide explains how to run the local Hardhat blockchain and deploy
`contracts/DeltaOTA.sol` for development.

## Prerequisites

From the repository root, install the Node.js dependencies once:

```powershell
npm install
```

## 1. Start Hardhat

Open a PowerShell terminal in the repository root and run:

```powershell
npx hardhat node
```

Keep this terminal open. Hardhat starts a local blockchain at:

```text
http://127.0.0.1:8545
```

It also prints funded development accounts. The deployment script uses the
first three standard Hardhat accounts as the authorized developers for the
2-of-3 approval contract.

## 2. Deploy DeltaOTA

Open a second PowerShell terminal in the repository root and run:

```powershell
npx hardhat run scripts/deploy.js --network localhost
```

The command prints the deployed contract address:

```text
DELTA_OTA CONTRACT ADDRESS: 0x...
```


## 3. Compile only

To compile the contract without starting the local blockchain, run:

```powershell
npx hardhat compile
```

The ABI and contract artifact are generated at:

```text
artifacts/contracts/DeltaOTA.sol/DeltaOTA.json
```

## Important notes

- Restarting `npx hardhat node` resets the local blockchain and removes all
  deployments. Run the deploy command again after a restart.
- The deployment script uses Hardhat test accounts. This setup is for local
  development only and must not be used on a public network.
- Stop the local blockchain with `Ctrl+C` in the Hardhat terminal.