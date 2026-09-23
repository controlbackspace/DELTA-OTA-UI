import hre from "hardhat";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";

/**
 * Day-1 baseline helper: propose v1.1 as Dev1 and approve as Dev2 so the
 * release goes Live (2-of-3 threshold needs two DISTINCT signers; the
 * deployer occupies Dev1/account #0, so approval must come from account #1).
 *
 * The golden hash is computed live from gateway/artifacts/dummy_patch.bin so
 * the gateway's integrity check passes byte-for-byte.
 *
 * Requires: hardhat node running + DELTA_CONTRACT_ADDRESS set (deploy output).
 * Fresh node per run: re-proposing v1.1 on a used chain reverts (duplicate guard).
 *
 * Usage: DELTA_CONTRACT_ADDRESS=0x... npx hardhat run scripts/propose-v11.js --network localhost
 *   REVOKE_RELEASE=1  ...then revoke v1.1 as Dev1 (Day-2 kill-switch setup)
 *   BAD_HASH=1        ...propose with a wrong golden hash (Day-2 mismatch setup)
 */
async function main() {
  const contractAddr = process.env.DELTA_CONTRACT_ADDRESS;
  if (!contractAddr) {
    throw new Error("DELTA_CONTRACT_ADDRESS is not set (run deploy.js first).");
  }

  const dummyPath = path.resolve("..", "gateway", "artifacts", "dummy_patch.bin");
  const goldenHashHex = createHash("sha256").update(readFileSync(dummyPath)).digest("hex");

  const versionBytes32 = hre.ethers.encodeBytes32String("v1.1");

  const [dev1, dev2] = await hre.ethers.getSigners();
  const contract = await hre.ethers.getContractAt("DeltaOTA", contractAddr);

  // Day-1 trap guard: without --network localhost this script talks to an
  // ephemeral in-process chain where no contract exists. State-changing calls
  // "succeed" vacuously and getRelease explodes with BAD_DATA. Fail loud here.
  const code = await hre.ethers.provider.getCode(contractAddr);
  if (code === "0x") {
    throw new Error(
      `No contract at ${contractAddr} - deploy first and pass --network localhost.`
    );
  }

  // Nonzero but wrong on purpose: the contract rejects an all-zero golden
  // hash at propose time, so BAD_HASH uses the hash of a wrong payload.
  const wrongHashHex = createHash("sha256").update("wrong-payload").digest("hex");
  const goldenBytes32 = process.env.BAD_HASH === "1" ? "0x" + wrongHashHex : "0x" + goldenHashHex;
  if (process.env.BAD_HASH === "1") {
    console.log("BAD_HASH=1: proposing with a wrong golden hash (mismatch setup).");
  }

  const tx1 = await contract
    .connect(dev1)
    .proposeRelease(versionBytes32, goldenBytes32, "ipfs://demo/dummy_patch.bin");
  await tx1.wait();
  console.log(`proposed v1.1 as ${dev1.address} (tx ${tx1.hash.slice(0, 18)}...)`);

  const tx2 = await contract.connect(dev2).approveRelease(versionBytes32);
  const receipt = await tx2.wait();
  console.log(`approved v1.1 as ${dev2.address} (block #${receipt.blockNumber})`);

  let lastBlock = receipt.blockNumber;
  if (process.env.REVOKE_RELEASE === "1") {
    const tx3 = await contract.connect(dev1).revokeRelease(versionBytes32);
    const revokeReceipt = await tx3.wait();
    lastBlock = revokeReceipt.blockNumber;
    console.log(`REVOKED v1.1 as ${dev1.address} (block #${revokeReceipt.blockNumber})`);
  }

  const rel = await contract.getRelease(versionBytes32);
  console.log(
    JSON.stringify(
      {
        version: "v1.1",
        goldenHash: goldenBytes32.slice(2),
        approvalCount: Number(rel.approvalCount),
        isLive: rel.isLive,
        isRevoked: rel.isRevoked,
        lastBlock,
        contract: contractAddr,
      },
      null,
      2
    )
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
