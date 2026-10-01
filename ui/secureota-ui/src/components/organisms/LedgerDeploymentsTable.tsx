import * as React from "react";
import { BookOpen, AlertTriangle, ShieldCheck, ShieldX } from "lucide-react";
import { CodeBadge } from "../atoms/CodeBadge";
import { StatusPill } from "../atoms/StatusPill";
import { cn } from "../../lib/utils";

export interface LedgerRelease {
  version: string;
  goldenHash: string;
  approvalCount: number;
  maxApprovals: number;
  isLive: boolean;
  isRevoked: boolean;
}

export interface LedgerDeploymentsTableProps {
  releases: LedgerRelease[];
  onExecuteKillSwitch: (version: string) => void;
  onApproveUpdate: (version: string) => void;
  /** Lowercased proposer per version (receipt.from at propose time). */
  proposerByVersion?: Record<string, string>;
  /** Currently connected wallet (any case) — used for the proposer guard. */
  connectedAddress?: string | null;
  /** Wallet connected AND not chain-verified as unauthorized. Any authorized
   *  developer may revoke (the contract has no proposer/approver restriction). */
  canRevoke?: boolean;
}

export const LedgerDeploymentsTable: React.FC<LedgerDeploymentsTableProps> = ({
  releases,
  onExecuteKillSwitch,
  onApproveUpdate,
  proposerByVersion = {},
  connectedAddress = null,
  canRevoke = false,
}) => {
  return (
    <div className="border-b border-[#1a2a3a] bg-[#060c18]">
      <div className="flex items-center gap-3 px-6 py-3 border-b border-[#1a2a3a]">
        <BookOpen className="w-4 h-4 text-violet-400" />
        <span className="text-[10px] uppercase tracking-wider text-violet-400 font-sans font-semibold">
          On-Chain Firmware Ledger
        </span>
        <span className="text-xs text-slate-600 font-mono">governance:0x4f3a...c7e2</span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="border-b border-[#1a2a3a] text-slate-500 text-[10px] uppercase tracking-wider">
              <th className="text-left px-6 py-3 font-medium">Version</th>
              <th className="text-left px-6 py-3 font-medium">Golden Hash</th>
              <th className="text-center px-6 py-3 font-medium">Approvals</th>
              <th className="text-center px-6 py-3 font-medium">Status</th>
              <th className="text-right px-6 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {releases.map((release) => (
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
                <td className="px-6 py-4 text-slate-400 max-w-[200px] truncate">
                  {release.goldenHash}
                </td>
                <td className="px-6 py-4 text-center">
                  <span
                    className={cn(
                      "font-semibold",
                      release.isLive || release.approvalCount >= release.maxApprovals
                        ? "text-emerald-400"
                        : "text-amber-400"
                    )}
                  >
                    {release.approvalCount}/{release.maxApprovals}
                  </span>
                </td>
                <td className="px-6 py-4 text-center">
                  {release.isRevoked ? (
                    <StatusPill color="rose" label="Revoked" dot />
                  ) : release.isLive ? (
                    <StatusPill color="emerald" label="Live" dot />
                  ) : (
                    <StatusPill color="amber" label="Pending" dot />
                  )}
                </td>
                <td className="px-6 py-4 text-right">
                  <div className="flex items-center justify-end gap-2">
                    {(() => {
                      if (release.isLive || release.isRevoked) return null;
                      const proposer = proposerByVersion[release.version.toLowerCase()];
                      const me = (connectedAddress || "").toLowerCase();
                      // 2-of-3 needs a DISTINCT second key: the proposer sees an
                      // inert chip (no wallet prompt, no gas) instead of Approve.
                      if (proposer && me && proposer === me) {
                        return (
                          <span
                            title="Proposer cannot approve their own release — switch to a different authorized dev key."
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-slate-800 bg-slate-900/40 text-slate-500 text-[10px] cursor-not-allowed"
                          >
                            <ShieldCheck className="w-3 h-3" />
                            Awaiting other dev (1/3)
                          </span>
                        );
                      }
                      return (
                        <button
                          type="button"
                          onClick={() => onApproveUpdate(release.version)}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded border border-emerald-800/40 bg-emerald-950/20 text-emerald-400 hover:bg-emerald-950/40 transition-all text-[10px]"
                        >
                          <ShieldCheck className="w-3 h-3" />
                          Approve
                        </button>
                      );
                    })()}
                    {!release.isRevoked && (
                      <button
                        type="button"
                        disabled={!canRevoke}
                        title={
                          canRevoke
                            ? `Revoke ${release.version} on-chain (any authorized developer).`
                            : "Connect an authorized developer wallet to revoke."
                        }
                        onClick={() => {
                          if (
                            window.confirm(
                              `Revoke ${release.version}?

This is permanent on-chain: the gateway destroys the staged artifacts and devices are refused. A fix needs a new version.`
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
            ))}
            {releases.length === 0 && (
              <tr>
                <td colSpan={5} className="px-6 py-8 text-center text-slate-600 font-sans text-sm">
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
