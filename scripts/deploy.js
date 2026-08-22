import hre from "hardhat";

async function main() {

  // Initial developer addresses for 2-of-3 multisig governance
  // These are extracted from default Hardhat localhost test accounts; tested the first three accs

  const dev1 = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266";
  const dev2 = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8";
  const dev3 = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC";

  console.log("\n===============================================");
  console.log(" Deploying DeltaOTA Smart Contract to Localhost");
  console.log("===============================================");
  console.log("Authorized Dev 1:", dev1);
  console.log("Authorized Dev 2:", dev2);
  console.log("Authorized Dev 3:", dev3);

  // Passing the developer addresses to the constructor of the DeltaOTA contract

  const DeltaOTA = await hre.ethers.getContractFactory("DeltaOTA");
  const deltaOTA = await DeltaOTA.deploy([dev1, dev2, dev3]);

  // Wait for deployment transaction confirmation
  await deltaOTA.waitForDeployment();

  // Get the deployed contract address
  const deployedAddress = await deltaOTA.getAddress();


  console.log("-----------------------------------------------");
  console.log(" DELTA_OTA CONTRACT ADDRESS:", deployedAddress);
  console.log("===============================================\n");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
