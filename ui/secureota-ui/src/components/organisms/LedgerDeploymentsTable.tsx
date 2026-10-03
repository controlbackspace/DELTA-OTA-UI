import * as React from "react";
import { BookOpen, AlertTriangle, ShieldCheck, ShieldX, Eye, FileCheck } from "lucide-react";
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
import type { PatchCheck } from "../../features/governance/patchVerify";

export interface LedgerRelease {
  version: string;
  goldenHash: string;
  approvalCount: number;
  maxApprovals: number;
  isLive: boolean;
  isRevoked: boolean;
  /** Download URL anchored on-chain by the proposer (patch host). */
  ipfsUrl?: string;
}

/** A patch check is only valid for the hash it was run against. */
export type StoredPatchCheck = PatchCheck & { forHash: string; checking?: boolean };

export interface LedgerDeploymentsTableProps {
  releases: LedgerRelease[];
  onExecuteKillSwitch: (version: string) => void;
  onApproveUpdate: (version: string) => void;
  /** Download the patch from the on-chain URL and compare it with the golden hash. */
  onVerifyPatch?: (version: string) => void;
  /** Follow a release's deployment (read-only, open to every author). */
  onTrack?: (version: string) => void;
  /** Version currently followed by the tracker. */
  trackedVersion?: string | null;
  /** Lowercased proposer of the newest proposal round, per lowercased version. */
  proposerByVersion?: Record<string, string>;
  /** Currently connected wallet (any case). */
  connectedAddress?: string | null;
  /** Chain-verified authorization of the connected wallet; null = unknown. */
  authorized?: boolean | null;
  /** hasSigned for the connected wallet, per lowercased version (pending releases). */
  signedByMe?: Record<string, boolean>;
  patchChecks?: Record<string, StoredPatchCheck>;
}

const hostOf = (url?: string): string => {
  if (!url) return "—";
  try {
    return new URL(url).host;
  } catch {
    return url.slice(0, 24);
  }
};

const PatchCell: React.FC<{
  release: LedgerRelease;
  check?: StoredPatchCheck;
  onVerify?: (v: string) => void;
}> = ({ release, check, onVerify }) => {
  const valid = check && check.forHash === release.goldenHash ? check : undefined;
  let badge: React.ReactNode = <span className="text-slate-600">not checked</span>;
  if (valid?.checking) badge = <span className="text-cyan-400">checking…</span>;
  else if (valid?.status === "verified") badge = <span className="text-emerald-400" title={valid.detail}>verified</span>;
  else if (valid?.status === "mismatch") badge = <span className="text-rose-400 font-semibold" title={valid.detail}>HASH MISMATCH</span>;
  else if (valid?.status === "unreachable") badge = <span className="text-amber-400" title={valid.detail}>unreachable</span>;

  return (
    <div className="flex flex-col items-start gap-1 text-[10px]">
      <span className="text-slate-500 max-w-[160px] truncate" title={release.ipfsUrl}>
        {hostOf(release.ipfsUrl)}
      </span>
      <span className="flex items-center gap-2">
        {badge}
        {onVerify && release.ipfsUrl && !valid?.checking && (
          <button
            type="button"
            onClick={() => onVerify(release.version)}
            title="Download the patch from the on-chain URL and compare its SHA-256 with the on-chain golden hash."
            className="flex items-center gap-1 px-1.5 py-0.5 rounded border border-cyan-800/40 text-cyan-400 hover:bg-cyan-950/30"
          >
            <FileCheck className="w-3 h-3" />
            Verify
          </button>
        )}
      </span>
    </div>
  );
};

export const LedgerDeploymentsTable: React.FC<LedgerDeploymentsTableProps> = ({
  releases,
  onExecuteKillSwitch,
  onApproveUpdate,
  onVerifyPatch,
  onTrack,
  trackedVersion = null,
  proposerByVersion = {},
  connectedAddress = null,
  authorized = null,
  signedByMe = {},
  patchChecks = {},
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
              <th className="text-left px-6 py-3 font-medium">Patch</th>
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
              const check = patchChecks[key];
              const mismatch = check && check.forHash === release.goldenHash && check.status === "mismatch";
              const pendingChip = (text: string, title: string) => (
                <span
                  title={title}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-slate-800 bg-slate-900/40 text-slate-500 text-[10px] cursor-default"
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
                    <PatchCell release={release} check={check} onVerify={onVerifyPatch} />
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2 flex-wrap">
                      {actions.canApprove && !mismatch && (
                        <button
                          type="button"
                          onClick={() => onApproveUpdate(release.version)}
                          title="Give the second signature. The console first checks the patch against the on-chain hash."
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-emerald-800/40 bg-emerald-950/20 text-emerald-400 hover:bg-emerald-950/40 transition-all text-[10px]"
                        >
                          <ShieldCheck className="w-3 h-3" />
                          Approve
                        </button>
                      )}
                      {actions.canApprove && mismatch &&
                        pendingChip("Blocked: hash mismatch", check?.detail ?? "The patch does not match the on-chain hash.")}
                      {!actions.canApprove && actions.approveBlock === "is-proposer" &&
                        pendingChip("Awaiting another developer", approveBlockText("is-proposer"))}
                      {!actions.canApprove && actions.approveBlock === "already-signed" &&
                        pendingChip("You signed - awaiting threshold", approveBlockText("already-signed"))}
                      {!actions.canApprove && actions.approveBlock === "already-live" &&
                        pendingChip("Approvals complete", approveBlockText("already-live"))}

                      {onTrack && (
                        <button
                          type="button"
                          onClick={() => onTrack(release.version)}
                          title="Follow this release through chain, gateway and device (read-only)."
                          className={cn(
                            "flex items-center gap-1.5 px-3 py-1.5 rounded border text-[10px] transition-all",
                            trackedVersion === release.version
                              ? "border-cyan-500/60 bg-cyan-950/40 text-cyan-300"
                              : "border-cyan-800/40 bg-cyan-950/10 text-cyan-400 hover:bg-cyan-950/30"
                          )}
                        >
                          <Eye className="w-3 h-3" />
                          {trackedVersion === release.version ? "Followed" : "Follow"}
                        </button>
                      )}

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
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-rose-800/40 bg-rose-950/20 text-rose-400 hover:bg-rose-950/40 transition-all text-[10px] disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-rose-950/20"
                        >
                          <ShieldX className="w-3 h-3" />
                          Kill
                        </button>
                      )}
                      {release.isRevoked && (
                        <span className="flex items-center gap-1.5 px-3 py-1.5 text-slate-600 text-[10px]">
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
                <td colSpan={7} className="px-6 py-8 text-center text-slate-600 font-sans text-sm">
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
