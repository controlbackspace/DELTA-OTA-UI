import "@nomicfoundation/hardhat-ethers";

// The SOP runner (gateway/sop) sets SOP_MOCHA_JSON to get a machine-readable
// test report; normal runs are unaffected.
const jsonReport = process.env.SOP_MOCHA_JSON;

export default {
  solidity: "0.8.20",
  ...(jsonReport ? { mocha: { reporter: "json", reporterOptions: { output: jsonReport } } } : {}),
};
