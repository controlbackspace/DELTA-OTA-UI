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
 */
async function main() {
  const contractAddr = process.env.DELTA_CONTRACT_ADDRESS;
  if (!contractAddr) {
    throw new Error("DELTA_CONTRACT_ADDRESS is not set (run deploy.js first).");
  }

  const dummyPath = path.resolve("..", "gateway", "artifacts", "dummy_patch.bin");
  const goldenHashHex = createHash("sha256").update(readFileSync(dummyPath)).digest("hex");

  const versionBytes32 = hre.ethers.encodeBytes32String("v1.1");
  const goldenBytes32 = "0x" + goldenHashHex;

  const [dev1, dev2] = await hre.ethers.getSigners();
  const contract = await hre.ethers.getContractAt("DeltaOTA", contractAddr);

  const tx1 = await contract
    .connect(dev1)
    .proposeRelease(versionBytes32, goldenBytes32, "ipfs://demo/dummy_patch.bin");
  await tx1.wait();
  console.log(`proposed v1.1 as ${dev1.address} (tx ${tx1.hash.slice(0, 18)}...)`);

  const tx2 = await contract.connect(dev2).approveRelease(versionBytes32);
  const receipt = await tx2.wait();
  console.log(`approved v1.1 as ${dev2.address} (block #${receipt.blockNumber})`);

  const rel = await contract.getRelease(versionBytes32);
  console.log(
    JSON.stringify(
      {
        version: "v1.1",
        goldenHash: goldenHashHex,
        approvalCount: Number(rel.approvalCount),
        isLive: rel.isLive,
        isRevoked: rel.isRevoked,
        approveBlock: receipt.blockNumber,
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
