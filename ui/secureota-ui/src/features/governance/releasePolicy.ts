/**
 * Who may do what with a release - pure functions, no React, no ethers.
 *
 * There are 3 authorized developers and a 2-of-3 threshold. Roles are never a
 * property of a console/device: for each release exactly one developer is the
 * proposer (their signature is #1), any other developer who has not signed may
 * give the second signature, any developer may revoke, and everyone else only
 * watches. The Ledger table, the action handlers and the tests all go through
 * here so every console reaches the same verdict from the same chain facts.
 */

export const THRESHOLD_M = 2;
export const TOTAL_DEVS_N = 3;

export interface ReleaseFacts {
  approvalCount: number;
  isLive: boolean;
  isRevoked: boolean;
  /** Proposer of the newest proposal round, lowercased; null when unknown. */
  proposer: string | null;
}

export interface ViewerFacts {
  /** Connected wallet address (any case); null = not connected. */
  address: string | null;
  /** Chain-verified authorization; null = unknown (no contract / node down). */
  authorized: boolean | null;
  /** hasSigned(version, address) for the current round; null = unknown. */
  hasSigned: boolean | null;
}

export type ApproveBlock =
  | "not-connected"
  | "not-authorized"
  | "revoked"
  | "already-live"
  | "is-proposer"
  | "already-signed";

export type RevokeBlock = "not-connected" | "not-authorized" | "revoked";

export type ViewerRole = "proposer" | "signed" | "can-approve" | "observer";

export interface ReleaseActions {
  role: ViewerRole;
  canApprove: boolean;
  approveBlock: ApproveBlock | null;
  canRevoke: boolean;
  revokeBlock: RevokeBlock | null;
  /** Following a release is always read-only and open to everyone. */
  canTrack: true;
}

export const sameAddress = (a: string | null | undefined, b: string | null | undefined): boolean =>
  !!a && !!b && a.toLowerCase() === b.toLowerCase();

export function releaseActions(release: ReleaseFacts, viewer: ViewerFacts): ReleaseActions {
  const connected = !!viewer.address;
  const isProposer = sameAddress(viewer.address, release.proposer);

  let approveBlock: ApproveBlock | null = null;
  if (!connected) approveBlock = "not-connected";
  else if (viewer.authorized === false) approveBlock = "not-authorized";
  else if (release.isRevoked) approveBlock = "revoked";
  else if (release.isLive) approveBlock = "already-live";
  else if (isProposer) approveBlock = "is-proposer";
  else if (viewer.hasSigned === true) approveBlock = "already-signed";

  let revokeBlock: RevokeBlock | null = null;
  if (!connected) revokeBlock = "not-connected";
  else if (viewer.authorized === false) revokeBlock = "not-authorized";
  else if (release.isRevoked) revokeBlock = "revoked";

  let role: ViewerRole = "observer";
  if (isProposer) role = "proposer";
  else if (viewer.hasSigned === true) role = "signed";
  else if (approveBlock === null) role = "can-approve";

  return {
    role,
    canApprove: approveBlock === null,
    approveBlock,
    canRevoke: revokeBlock === null,
    revokeBlock,
    canTrack: true,
  };
}

const APPROVE_TEXT: Record<ApproveBlock, string> = {
  "not-connected": "Connect an authorized developer wallet to approve.",
  "not-authorized": "The connected wallet is not an authorized developer on this contract.",
  revoked: "This release was revoked - it cannot be approved. Propose a new round.",
  "already-live": "Already live: the required approvals are complete.",
  "is-proposer": "You proposed this release (signature 1). A different developer must approve it.",
  "already-signed": "You already signed this release.",
};

export const approveBlockText = (b: ApproveBlock): string => APPROVE_TEXT[b];

const REVOKE_TEXT: Record<RevokeBlock, string> = {
  "not-connected": "Connect an authorized developer wallet to revoke.",
  "not-authorized": "The connected wallet is not an authorized developer on this contract.",
  revoked: "Already revoked - nothing to do.",
};

export const revokeBlockText = (b: RevokeBlock): string => REVOKE_TEXT[b];

/** "1 of 2 required (3 developers)" - one wording everywhere. */
export const approvalsLabel = (count: number): string =>
  `${count} of ${THRESHOLD_M} required (${TOTAL_DEVS_N} developers)`;

export function statusLabel(r: Pick<ReleaseFacts, "approvalCount" | "isLive" | "isRevoked">): string {
  if (r.isRevoked) return "Revoked";
  if (r.isLive) return "Live - approvals complete";
  const missing = Math.max(0, THRESHOLD_M - r.approvalCount);
  return `Pending - needs ${missing} more approval${missing === 1 ? "" : "s"}`;
}

/** Map a raw contract/wallet failure to the one thing the author should know.
 *  Returns null when the message is not a known governance outcome. */
export function governanceRevertText(raw: string): string | null {
  const low = raw.toLowerCase();
  if (low.includes("already live")) return "Already live - another developer's approval landed first. Nothing was lost; the ledger is refreshing.";
  if (low.includes("already signed")) return "You already signed this release.";
  if (low.includes("cannot approve a revoked") || low.includes("already revoked"))
    return "This release was revoked in the meantime.";
  if (low.includes("does not exist")) return "That version is not on this contract (wrong contract address?).";
  return null;
}

export interface ProposalEvent {
  version: string;
  proposer: string;
  ipfsUrl: string;
  goldenHash: string;
  blockNumber: number;
  logIndex: number;
}

/** Newest proposal per version. A revoked version can be proposed again, so
 *  the first event is NOT the current one. Keys are lowercased versions. */
export function newestProposals(events: ProposalEvent[]): Map<string, ProposalEvent> {
  const out = new Map<string, ProposalEvent>();
  for (const e of events) {
    const key = e.version.toLowerCase();
    const cur = out.get(key);
    if (!cur || e.blockNumber > cur.blockNumber || (e.blockNumber === cur.blockNumber && e.logIndex > cur.logIndex)) {
      out.set(key, { ...e, proposer: e.proposer.toLowerCase() });
    }
  }
  return out;
}
