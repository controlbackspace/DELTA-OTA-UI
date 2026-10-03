import * as React from "react";
import { BookOpen, AlertTriangle, ShieldCheck, ShieldX } from "lucide-react";
import { CodeBadge } from "../atoms/CodeBadge";
import { StatusPill } from "../atoms/StatusPill";
import { cn } from "../../lib/utils";
import { truncateAddress } from "../../lib/web3Payloads";
import {
  THRESHOLD_M,
  TOTAL_DEVS_N,
  approveBlockText,
  releaseActions,
  revokeBlockText,
  sameAddress,
  statusLabel,
} from "../../features/governance/releasePolicy";

export interface LedgerRelease {
  version: string;
  goldenHash: string;
  approvalCount: number;
  maxApprovals: number;
  isLive: boolean;
  isRevoked: boolean;
  /** Download URL anchored on-chain by the proposer. */
  ipfsUrl?: string;
}

export interface LedgerDeploymentsTableProps {
  releases: LedgerRelease[];
  onExecuteKillSwitch: (version: string) => void;
  onApproveUpdate: (version: string) => void;
  /** Lowercased proposer of the newest proposal round, per lowercased version. */
  proposerByVersion?: Record<string, string>;
  /** Currently connected wallet (any case). */
  connectedAddress?: string | null;
  /** Chain-verified authorization of the connected wallet; null = unknown. */
  authorized?: boolean | null;
  /** hasSigned for the connected wallet, per lowercased version (pending releases). */
  signedByMe?: Record<string, boolean>;
}

// One size for every action in the row: equal height and width, so the buttons
// line up from row to row whichever mix of Approve / Kill / status shows.
const ACTION =
  "inline-flex items-center justify-center gap-1.5 h-8 w-[112px] shrink-0 rounded border font-sans text-[10px] whitespace-nowrap transition-colors";

export const LedgerDeploymentsTable: React.FC<LedgerDeploymentsTableProps> = ({
  releases,
  onExecuteKillSwitch,
  onApproveUpdate,
  proposerByVersion = {},
  connectedAddress = null,
  authorized = null,
  signedByMe = {},
}) => {
  return (
    <div className="border-b border-[#1a2a3a] bg-[#060c18]">
      <div className="flex items-center gap-3 px-6 py-3 border-b border-[#1a2a3a]">
        <BookOpen className="w-4 h-4 text-violet-400" />
        <span className="text-[10px] uppercase tracking-wider text-violet-400 font-sans font-semibold">
          On-Chain Firmware Ledger
        </span>
        <span className="text-xs text-slate-600 font-sans">
          {THRESHOLD_M}-of-{TOTAL_DEVS_N} developers must sign; the proposer is signature 1
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="border-b border-[#1a2a3a] text-slate-500 text-[10px] uppercase tracking-wider">
              <th className="text-left px-6 py-3 font-medium">Version</th>
              <th className="text-left px-6 py-3 font-medium">Proposer</th>
              <th className="text-left px-6 py-3 font-medium">Golden Hash</th>
              <th className="text-center px-6 py-3 font-medium">Approvals</th>
              <th className="text-center px-6 py-3 font-medium">Status</th>
              <th className="text-right px-6 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {releases.map((release) => {
              const key = release.version.toLowerCase();
              const proposer = proposerByVersion[key] ?? null;
              const actions = releaseActions(
                {
                  approvalCount: release.approvalCount,
                  isLive: release.isLive,
                  isRevoked: release.isRevoked,
                  proposer,
                },
                { address: connectedAddress, authorized, hasSigned: signedByMe[key] ?? null }
              );
              const statusChip = (text: string, title: string) => (
                <span
                  title={title}
                  className={cn(ACTION, "border-slate-800 bg-slate-900/40 text-slate-500 cursor-default")}
                >
                  <ShieldCheck className="w-3 h-3" />
                  {text}
                </span>
              );
              return (
                <tr
                  key={release.version}
                  className={cn(
                    "border-b border-[#1a2a3a] transition-colors",
                    release.isRevoked ? "bg-rose-950/5" : "hover:bg-[#0a1525]"
                  )}
                >
                  <td className="px-6 py-4">
                    <CodeBadge variant={release.isRevoked ? "danger" : release.isLive ? "success" : "warning"}>
                      {release.version}
                    </CodeBadge>
                  </td>
                  <td className="px-6 py-4 text-slate-400">
                    {proposer ? (
                      <span title={proposer}>
                        {truncateAddress(proposer)}
                        {sameAddress(proposer, connectedAddress) && <span className="ml-1 text-cyan-400">(you)</span>}
                      </span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-slate-400 max-w-[200px] truncate" title={release.goldenHash}>
                    {release.goldenHash}
                  </td>
                  <td className="px-6 py-4 text-center">
                    <span
                      className={cn(
                        "font-semibold",
                        release.isLive || release.approvalCount >= THRESHOLD_M ? "text-emerald-400" : "text-amber-400"
                      )}
                    >
                      {release.approvalCount} of {THRESHOLD_M}
                    </span>
                    <div className="text-[9px] text-slate-600 font-sans">{TOTAL_DEVS_N} developers</div>
                  </td>
                  <td className="px-6 py-4 text-center" title={statusLabel(release)}>
                    {release.isRevoked ? (
                      <StatusPill color="rose" label="Revoked" dot />
                    ) : release.isLive ? (
                      <StatusPill color="emerald" label="Live" dot />
                    ) : (
                      <StatusPill color="amber" label="Pending" dot />
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center justify-end gap-2 flex-nowrap">
                      {actions.canApprove && (
                        <button
                          type="button"
                          onClick={() => onApproveUpdate(release.version)}
                          title="Give the second signature (2-of-3)."
                          className={cn(ACTION, "border-emerald-800/40 bg-emerald-950/20 text-emerald-400 hover:bg-emerald-950/40")}
                        >
                          <ShieldCheck className="w-3 h-3" />
                          Approve
                        </button>
                      )}
                      {!actions.canApprove && actions.approveBlock === "is-proposer" &&
                        statusChip("Awaiting others", approveBlockText("is-proposer"))}
                      {!actions.canApprove && actions.approveBlock === "already-signed" &&
                        statusChip("You signed", approveBlockText("already-signed"))}
                      {!actions.canApprove && actions.approveBlock === "already-live" &&
                        statusChip("Approved", approveBlockText("already-live"))}

                      {!release.isRevoked && (
                        <button
                          type="button"
                          disabled={!actions.canRevoke}
                          title={
                            actions.canRevoke
                              ? `Revoke ${release.version} on-chain (any authorized developer).`
                              : actions.revokeBlock
                                ? revokeBlockText(actions.revokeBlock)
                                : ""
                          }
                          onClick={() => {
                            if (
                              window.confirm(
                                `Revoke ${release.version}?\n\nThis is permanent on-chain: the gateway destroys the staged artifacts and devices are refused. A fix needs a new proposal.`
                              )
                            )
                              onExecuteKillSwitch(release.version);
                          }}
                          className={cn(
                            ACTION,
                            "border-rose-800/40 bg-rose-950/20 text-rose-400 hover:bg-rose-950/40 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-rose-950/20"
                          )}
                        >
                          <ShieldX className="w-3 h-3" />
                          Kill
                        </button>
                      )}
                      {release.isRevoked && (
                        <span className={cn(ACTION, "border-transparent text-slate-600 cursor-default")}>
                          <AlertTriangle className="w-3 h-3" />
                          Revoked
                        </span>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
            {releases.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-slate-600 font-sans text-sm">
                  No firmware releases found on the ledger.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
