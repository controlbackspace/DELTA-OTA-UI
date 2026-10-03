// Contract behaviour behind SOP 3: the ledger is the single authority on whether
// a release may be distributed. Run: npx hardhat test
import hre from "hardhat";
import assert from "node:assert/strict";

const { ethers } = hre;
const v = (tag) => ethers.encodeBytes32String(tag);
const hash = (n) => ethers.zeroPadValue(ethers.toBeHex(n), 32);
const ZERO32 = ethers.ZeroHash;

describe("DeltaOTA contract", () => {
  let a, b, c, outsider, contract;

  beforeEach(async () => {
    [a, b, c, outsider] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("DeltaOTA");
    contract = await Factory.deploy([a.address, b.address, c.address]);
    await contract.waitForDeployment();
  });

  const as = (s) => contract.connect(s);
  const events = (name) => contract.queryFilter(contract.filters[name]());

  describe("governance parameters", () => {
    it("is a fixed 2-of-3 multisig", async () => {
      assert.equal(await contract.thresholdM(), 2n);
      assert.equal(await contract.totalDevelopersN(), 3n);
    });

    it("whitelists exactly the three constructor developers", async () => {
      for (const s of [a, b, c]) assert.equal(await contract.authorizedDevelopers(s.address), true);
      assert.equal(await contract.authorizedDevelopers(outsider.address), false);
      assert.equal((await events("DeveloperStatusUpdated")).length, 3);
    });

    it("refuses a deployment with the wrong number of developers", async () => {
      const Factory = await ethers.getContractFactory("DeltaOTA");
      await assert.rejects(Factory.deploy([a.address, b.address]), /Exactly 3 initial developers/);
      await assert.rejects(Factory.deploy([a.address, b.address, c.address, outsider.address]), /Exactly 3 initial developers/);
    });

    it("refuses the zero address and duplicate developers", async () => {
      const Factory = await ethers.getContractFactory("DeltaOTA");
      await assert.rejects(Factory.deploy([a.address, b.address, ethers.ZeroAddress]), /Invalid zero address/);
      await assert.rejects(Factory.deploy([a.address, a.address, c.address]), /Duplicate developer/);
    });
  });

  describe("proposing", () => {
    it("records the release with the proposer's signature as the first approval", async () => {
      await (await as(a).proposeRelease(v("v1.1"), hash(1), "http://host/p.bin")).wait();
      const r = await contract.getRelease(v("v1.1"));
      assert.equal(r.version, v("v1.1"));
      assert.equal(r.goldenHash, hash(1));
      assert.equal(r.ipfsUrl, "http://host/p.bin");
      assert.equal(r.approvalCount, 1n);
      assert.equal(r.isLive, false);
      assert.equal(r.isRevoked, false);
      assert.equal(await contract.hasSigned(v("v1.1"), a.address), true);
      assert.equal(await contract.hasSigned(v("v1.1"), b.address), false);
    });

    it("emits ReleaseProposed and ReleaseApproved with the right arguments", async () => {
      await (await as(b).proposeRelease(v("v1.1"), hash(7), "u")).wait();
      const [proposed] = await events("ReleaseProposed");
      assert.equal(proposed.args.version, v("v1.1"));
      assert.equal(proposed.args.goldenHash, hash(7));
      assert.equal(proposed.args.proposer, b.address);
      const [approved] = await events("ReleaseApproved");
      assert.equal(approved.args.approver, b.address);
      assert.equal(approved.args.currentApprovals, 1n);
    });

    it("rejects an empty golden hash", async () => {
      await assert.rejects(as(a).proposeRelease(v("v1.1"), ZERO32, "u"), /Golden Hash cannot be empty/);
    });

    it("rejects a caller who is not a registered developer", async () => {
      await assert.rejects(as(outsider).proposeRelease(v("v1.1"), hash(1), "u"), /not a registered developer/);
    });

    it("never lets a pending or live version be overwritten", async () => {
      await (await as(a).proposeRelease(v("v1.1"), hash(1), "u")).wait();
      await assert.rejects(as(b).proposeRelease(v("v1.1"), hash(2), "u"), /already exists/);
      await (await as(b).approveRelease(v("v1.1"))).wait();
      await assert.rejects(as(c).proposeRelease(v("v1.1"), hash(3), "u"), /already exists/);
      assert.equal((await contract.getRelease(v("v1.1"))).goldenHash, hash(1));
    });
  });

  describe("approving (the 2-of-3 threshold)", () => {
    beforeEach(async () => {
      await (await as(a).proposeRelease(v("v1.1"), hash(1), "http://host/p.bin")).wait();
    });

    it("stays pending after one signature and goes live exactly at the second", async () => {
      assert.equal((await contract.getRelease(v("v1.1"))).isLive, false);
      await (await as(b).approveRelease(v("v1.1"))).wait();
      const r = await contract.getRelease(v("v1.1"));
      assert.equal(r.isLive, true);
      assert.equal(r.approvalCount, 2n);
    });

    it("announces the promotion once, with the metadata the gateway needs", async () => {
      assert.equal((await events("ReleasePromotedToLive")).length, 0);
      await (await as(c).approveRelease(v("v1.1"))).wait();
      const promoted = await events("ReleasePromotedToLive");
      assert.equal(promoted.length, 1);
      assert.equal(promoted[0].args.version, v("v1.1"));
      assert.equal(promoted[0].args.goldenHash, hash(1));
      assert.equal(promoted[0].args.ipfsUrl, "http://host/p.bin");
    });

    it("counts a developer's signature only once", async () => {
      await assert.rejects(as(a).approveRelease(v("v1.1")), /already signed/);
      assert.equal((await contract.getRelease(v("v1.1"))).approvalCount, 1n);
    });

    it("refuses outsiders, unknown versions and approvals after the release is live", async () => {
      await assert.rejects(as(outsider).approveRelease(v("v1.1")), /not a registered developer/);
      await assert.rejects(as(b).approveRelease(v("v9.9")), /does not exist/);
      await (await as(b).approveRelease(v("v1.1"))).wait();
      await assert.rejects(as(c).approveRelease(v("v1.1")), /already Live/);
      assert.equal((await contract.getRelease(v("v1.1"))).approvalCount, 2n);
    });

    it("keeps releases independent of each other", async () => {
      await (await as(b).proposeRelease(v("v1.2"), hash(2), "u")).wait();
      await (await as(c).approveRelease(v("v1.2"))).wait();
      assert.equal((await contract.getRelease(v("v1.2"))).isLive, true);
      assert.equal((await contract.getRelease(v("v1.1"))).isLive, false);
    });
  });

  describe("revocation (the kill switch)", () => {
    it("strips live status immediately and is final for that round", async () => {
      await (await as(a).proposeRelease(v("v1.1"), hash(1), "u")).wait();
      await (await as(b).approveRelease(v("v1.1"))).wait();
      await (await as(c).revokeRelease(v("v1.1"))).wait();
      const r = await contract.getRelease(v("v1.1"));
      assert.equal(r.isRevoked, true);
      assert.equal(r.isLive, false);
      await assert.rejects(as(a).approveRelease(v("v1.1")), /revoked/);
      await assert.rejects(as(a).revokeRelease(v("v1.1")), /already revoked/);
    });

    it("emits ReleaseRevoked naming the revoker", async () => {
      await (await as(a).proposeRelease(v("v1.1"), hash(1), "u")).wait();
      await (await as(b).revokeRelease(v("v1.1"))).wait();
      const [e] = await events("ReleaseRevoked");
      assert.equal(e.args.version, v("v1.1"));
      assert.equal(e.args.revoker, b.address);
    });

    it("needs no second signature, but only developers can do it", async () => {
      await (await as(a).proposeRelease(v("v1.1"), hash(1), "u")).wait();
      await assert.rejects(as(outsider).revokeRelease(v("v1.1")), /not a registered developer/);
      await assert.rejects(as(a).revokeRelease(v("v9.9")), /does not exist/);
      await (await as(c).revokeRelease(v("v1.1"))).wait();   // a pending release, one developer
      assert.equal((await contract.getRelease(v("v1.1"))).isRevoked, true);
    });

    it("allows a fixed re-proposal of a revoked version as a fresh round", async () => {
      await (await as(a).proposeRelease(v("v1.1"), hash(1), "old")).wait();
      await (await as(b).revokeRelease(v("v1.1"))).wait();
      await (await as(c).proposeRelease(v("v1.1"), hash(2), "fixed")).wait();
      const r = await contract.getRelease(v("v1.1"));
      assert.equal(r.goldenHash, hash(2));
      assert.equal(r.isRevoked, false);
      assert.equal(r.approvalCount, 1n);
      assert.equal(await contract.revision(v("v1.1")), 1n);
      assert.equal(await contract.hasSigned(v("v1.1"), a.address), false, "old signatures do not carry over");
    });
  });

  it("reads an unknown version as an empty record", async () => {
    const r = await contract.getRelease(v("never"));
    assert.equal(r.version, ZERO32);
    assert.equal(r.approvalCount, 0n);
    assert.equal(r.isLive, false);
  });
});
