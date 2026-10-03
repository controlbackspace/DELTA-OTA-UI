// Three authorized developers acting on one contract, including the races two
// independent consoles can produce. Run: npx hardhat test
import hre from "hardhat";
import assert from "node:assert/strict";

const { ethers } = hre;
const v = (tag) => ethers.encodeBytes32String(tag);
const hash = (n) => ethers.zeroPadValue(ethers.toBeHex(n), 32);
const GAS = { gasLimit: 500000 }; // explicit: skip estimation so a doomed tx still gets mined

// Send txs with automine off and mine them into ONE block, in the given order.
// Returns receipts (status 1 = executed, 0 = reverted in that block).
async function sameBlock(sends) {
  await hre.network.provider.send("evm_setAutomine", [false]);
  try {
    const txs = [];
    for (const send of sends) txs.push(await send());
    await hre.network.provider.send("evm_mine");
    const receipts = [];
    for (const tx of txs) receipts.push(await ethers.provider.getTransactionReceipt(tx.hash));
    return receipts;
  } finally {
    await hre.network.provider.send("evm_setAutomine", [true]);
  }
}

describe("DeltaOTA - three authors, independent consoles", () => {
  let a, b, c, outsider, contract;

  beforeEach(async () => {
    [a, b, c, outsider] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("DeltaOTA");
    contract = await Factory.deploy([a.address, b.address, c.address]);
    await contract.waitForDeployment();
  });

  const as = (signer) => contract.connect(signer);
  const state = async (tag) => {
    const r = await contract.getRelease(v(tag));
    return { count: Number(r.approvalCount), live: r.isLive, revoked: r.isRevoked, hash: r.goldenHash, url: r.ipfsUrl };
  };
  const promoted = async () => (await contract.queryFilter(contract.filters.ReleasePromotedToLive())).length;

  it("proposer is signature 1, cannot approve their own release; either other author completes it", async () => {
    await (await as(a).proposeRelease(v("v1.1"), hash(1), "http://a/p.bin")).wait();
    assert.deepEqual(await state("v1.1"), { count: 1, live: false, revoked: false, hash: hash(1), url: "http://a/p.bin" });
    assert.equal(await contract.hasSigned(v("v1.1"), a.address), true);
    await assert.rejects(as(a).approveRelease(v("v1.1")), /already signed/i);

    await (await as(c).approveRelease(v("v1.1"))).wait(); // the THIRD author approves: one more is enough
    const s = await state("v1.1");
    assert.equal(s.live, true);
    assert.equal(s.count, 2);
  });

  it("two authors approving in the same block: exactly one wins, one ReleasePromotedToLive", async () => {
    await (await as(a).proposeRelease(v("v1.1"), hash(1), "u")).wait();
    const receipts = await sameBlock([
      () => as(b).approveRelease(v("v1.1"), GAS),
      () => as(c).approveRelease(v("v1.1"), GAS),
    ]);
    const statuses = receipts.map((r) => r.status).sort();
    assert.deepEqual(statuses, [0, 1], "one executes, the other reverts (already Live)");
    const s = await state("v1.1");
    assert.equal(s.live, true);
    assert.equal(s.count, 2, "the loser must NOT add a third signature");
    assert.equal(await promoted(), 1);

    // the loser, retrying afterwards, gets the revert the console maps to "Already live"
    const loser = receipts[0].status === 0 ? b : c;
    await assert.rejects(as(loser).approveRelease(v("v1.1")), /already live/i);
  });

  it("approve vs revoke in the same block: whichever is first decides, final state is never Live-and-Revoked", async () => {
    // revoke first -> approve reverts, release ends revoked, never live
    await (await as(a).proposeRelease(v("v1.1"), hash(1), "u")).wait();
    let r = await sameBlock([
      () => as(c).revokeRelease(v("v1.1"), GAS),
      () => as(b).approveRelease(v("v1.1"), GAS),
    ]);
    assert.deepEqual(r.map((x) => x.status), [1, 0]);
    let s = await state("v1.1");
    assert.equal(s.revoked, true);
    assert.equal(s.live, false);
    assert.equal(await promoted(), 0);

    // approve first -> goes live, then the revoke strips it
    await (await as(a).proposeRelease(v("v1.2"), hash(2), "u")).wait();
    r = await sameBlock([
      () => as(b).approveRelease(v("v1.2"), GAS),
      () => as(c).revokeRelease(v("v1.2"), GAS),
    ]);
    assert.deepEqual(r.map((x) => x.status), [1, 1]);
    s = await state("v1.2");
    assert.equal(s.revoked, true);
    assert.equal(s.live, false);
    assert.equal(await promoted(), 1, "it did go live for one block before the revoke");
  });

  it("every author can revoke a pending release and a live one; revoked cannot be approved or revoked again", async () => {
    await (await as(a).proposeRelease(v("v1.1"), hash(1), "u")).wait();
    await (await as(c).revokeRelease(v("v1.1"))).wait(); // pending, revoked by a non-proposer
    assert.equal((await state("v1.1")).revoked, true);
    await assert.rejects(as(b).approveRelease(v("v1.1")), /revoked/i);
    await assert.rejects(as(a).revokeRelease(v("v1.1")), /already revoked/i);

    await (await as(b).proposeRelease(v("v1.2"), hash(2), "u")).wait();
    await (await as(a).approveRelease(v("v1.2"))).wait(); // live
    await (await as(c).revokeRelease(v("v1.2"))).wait(); // third author revokes a live release
    const s = await state("v1.2");
    assert.equal(s.revoked, true);
    assert.equal(s.live, false);
  });

  it("re-proposal after a revoke is a new round with a new proposer; old signatures do not carry over", async () => {
    await (await as(a).proposeRelease(v("v1.1"), hash(1), "http://a/old.bin")).wait();
    await (await as(b).approveRelease(v("v1.1"))).wait();
    await (await as(c).revokeRelease(v("v1.1"))).wait();

    await assert.rejects(as(a).proposeRelease(v("v1.1"), hash(9), "u").then(() => as(a).proposeRelease(v("v1.1"), hash(9), "u")), /already exists/i);
    // (the first re-proposal above succeeded; the duplicate must fail)

    assert.equal(await contract.revision(v("v1.1")), 1n);
    assert.equal(await contract.hasSigned(v("v1.1"), b.address), false, "b signed round 0 only");
    assert.equal(await contract.hasSigned(v("v1.1"), a.address), true, "a is proposer of round 1");
    const s = await state("v1.1");
    assert.equal(s.count, 1);
    assert.equal(s.hash, hash(9));
    await (await as(b).approveRelease(v("v1.1"))).wait(); // b may sign again in the new round
    assert.equal((await state("v1.1")).live, true);
  });

  it("live and pending releases cannot be overwritten by another proposal", async () => {
    await (await as(a).proposeRelease(v("v1.1"), hash(1), "u")).wait();
    await assert.rejects(as(b).proposeRelease(v("v1.1"), hash(2), "u"), /already exists/i); // pending
    await (await as(b).approveRelease(v("v1.1"))).wait();
    await assert.rejects(as(c).proposeRelease(v("v1.1"), hash(3), "u"), /already exists/i); // live
    assert.equal((await state("v1.1")).hash, hash(1));
  });

  it("only the three developers can act", async () => {
    await assert.rejects(as(outsider).proposeRelease(v("v9"), hash(1), "u"), /unauthorized|not a registered developer/i);
    await (await as(a).proposeRelease(v("v1.1"), hash(1), "u")).wait();
    await assert.rejects(as(outsider).approveRelease(v("v1.1")), /unauthorized|not a registered developer/i);
    await assert.rejects(as(outsider).revokeRelease(v("v1.1")), /unauthorized|not a registered developer/i);
  });

  it("events give every console the same version list and the NEWEST proposer (what the UI scans)", async () => {
    await (await as(a).proposeRelease(v("v1.1"), hash(1), "u1")).wait();
    await (await as(b).proposeRelease(v("v1.2"), hash(2), "u2")).wait();
    await (await as(c).revokeRelease(v("v1.1"))).wait();
    await (await as(c).proposeRelease(v("v1.1"), hash(3), "u3")).wait(); // re-proposed by a different author

    const logs = await contract.queryFilter(contract.filters.ReleaseProposed(), 0);
    const newest = new Map();
    for (const l of logs) newest.set(ethers.decodeBytes32String(l.args.version), l.args.proposer);
    assert.deepEqual([...newest.keys()].sort(), ["v1.1", "v1.2"]);
    assert.equal(newest.get("v1.1"), c.address, "newest proposal wins, not the first");
    assert.equal(newest.get("v1.2"), b.address);
  });
});
