// Run: npm test   (Node's built-in runner; Node 22.6+ strips the types natively)
import test from "node:test";
import assert from "node:assert/strict";
import {
  approvalsLabel,
  approveBlockText,
  governanceRevertText,
  newestProposals,
  releaseActions,
  sameAddress,
  statusLabel,
  type ReleaseFacts,
  type ViewerFacts,
} from "../src/features/governance/releasePolicy.ts";

const A = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266";
const B = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8";
const C = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC";
const OUTSIDER = "0x90F79bf6EB2c4f870365E785982E1f101E93b906";

const pending: ReleaseFacts = { approvalCount: 1, isLive: false, isRevoked: false, proposer: A.toLowerCase() };
const live: ReleaseFacts = { approvalCount: 2, isLive: true, isRevoked: false, proposer: A.toLowerCase() };
const revoked: ReleaseFacts = { approvalCount: 2, isLive: false, isRevoked: true, proposer: A.toLowerCase() };

const viewer = (address: string | null, over: Partial<ViewerFacts> = {}): ViewerFacts => ({
  address,
  authorized: address === OUTSIDER ? false : address ? true : null,
  hasSigned: false,
  ...over,
});

test("pending: proposer cannot approve, the other two authors can", () => {
  const a = releaseActions(pending, viewer(A, { hasSigned: true }));
  assert.equal(a.role, "proposer");
  assert.equal(a.canApprove, false);
  assert.equal(a.approveBlock, "is-proposer");
  assert.equal(a.canRevoke, true);
  for (const dev of [B, C]) {
    const r = releaseActions(pending, viewer(dev));
    assert.equal(r.canApprove, true, dev);
    assert.equal(r.role, "can-approve");
    assert.equal(r.canRevoke, true);
  }
});

test("pending: an author who already signed cannot sign twice", () => {
  const r = releaseActions(pending, viewer(B, { hasSigned: true }));
  assert.equal(r.canApprove, false);
  assert.equal(r.approveBlock, "already-signed");
  assert.equal(r.role, "signed");
});

test("live: nobody can approve (the 3rd author is an observer who can still revoke)", () => {
  for (const dev of [A, B, C]) {
    const r = releaseActions(live, viewer(dev, { hasSigned: dev !== C }));
    assert.equal(r.canApprove, false, dev);
    assert.equal(r.canRevoke, true, dev);
  }
  assert.equal(releaseActions(live, viewer(C)).approveBlock, "already-live");
});

test("revoked: no approve, no second revoke, tracking still allowed", () => {
  for (const dev of [A, B, C]) {
    const r = releaseActions(revoked, viewer(dev));
    assert.equal(r.canApprove, false);
    assert.equal(r.approveBlock, "revoked");
    assert.equal(r.canRevoke, false);
    assert.equal(r.revokeBlock, "revoked");
    assert.equal(r.canTrack, true);
  }
});

test("not connected / not authorized", () => {
  const off = releaseActions(pending, viewer(null));
  assert.equal(off.canApprove, false);
  assert.equal(off.approveBlock, "not-connected");
  assert.equal(off.canRevoke, false);
  assert.equal(off.canTrack, true);

  const out = releaseActions(pending, viewer(OUTSIDER));
  assert.equal(out.approveBlock, "not-authorized");
  assert.equal(out.revokeBlock, "not-authorized");
});

test("unknown authorization (node down) does not block; the contract is the judge", () => {
  const r = releaseActions(pending, viewer(B, { authorized: null, hasSigned: null }));
  assert.equal(r.canApprove, true);
  assert.equal(r.canRevoke, true);
});

test("re-proposed after a revoke: a new round, previous signers may sign again", () => {
  const round2: ReleaseFacts = { ...pending, proposer: B.toLowerCase() };
  assert.equal(releaseActions(round2, viewer(B, { hasSigned: true })).approveBlock, "is-proposer");
  assert.equal(releaseActions(round2, viewer(A, { hasSigned: false })).canApprove, true);
});

test("address comparison ignores case and rejects empties", () => {
  assert.equal(sameAddress(A, A.toLowerCase()), true);
  assert.equal(sameAddress(A, B), false);
  assert.equal(sameAddress(null, A), false);
  assert.equal(sameAddress("", ""), false);
});

test("newestProposals: the latest round wins, not the first", () => {
  const e = (version: string, proposer: string, blockNumber: number, logIndex = 0) => ({
    version, proposer, ipfsUrl: `http://x/${blockNumber}`, goldenHash: "0x" + "1".repeat(64), blockNumber, logIndex,
  });
  const m = newestProposals([e("v1.1", A, 5), e("v1.2", B, 6), e("v1.1", C, 9), e("v1.1", B, 9, 1)]);
  assert.equal(m.size, 2);
  assert.equal(m.get("v1.1")?.proposer, B.toLowerCase());
  assert.equal(m.get("v1.1")?.blockNumber, 9);
  assert.equal(m.get("v1.2")?.proposer, B.toLowerCase());
});

test("copy helpers", () => {
  assert.equal(approvalsLabel(1), "1 of 2 required (3 developers)");
  assert.equal(statusLabel(pending), "Pending - needs 1 more approval");
  assert.equal(statusLabel({ approvalCount: 0, isLive: false, isRevoked: false }), "Pending - needs 2 more approvals");
  assert.equal(statusLabel(live), "Live - approvals complete");
  assert.equal(statusLabel(revoked), "Revoked");
  assert.match(approveBlockText("is-proposer"), /different developer/);
});

test("governance reverts get one clear sentence; unknown errors pass through", () => {
  assert.match(governanceRevertText("execution reverted: Governance Error: Release is already Live") ?? "", /Already live/);
  assert.match(governanceRevertText("Governance Error: Developer has already signed this release") ?? "", /already signed/);
  assert.match(governanceRevertText("Governance Error: Cannot approve a revoked release") ?? "", /revoked/);
  assert.equal(governanceRevertText("insufficient funds"), null);
});
