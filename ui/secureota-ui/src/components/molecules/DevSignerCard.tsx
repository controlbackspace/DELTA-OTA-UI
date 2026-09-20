import * as React from "react";
import { ShieldCheck, UserCheck } from "lucide-react";
import { CodeBadge } from "../atoms/CodeBadge";
import { StatusPill } from "../atoms/StatusPill";
import { cn } from "../../lib/utils";

export interface DevSignerCardProps {
  devIndex: number;
  address: string;
  isProposer: boolean;
  isConnected?: boolean;
  onSelect: () => void;
}

export const DevSignerCard: React.FC<DevSignerCardProps> = ({
  devIndex,
  address,
  isProposer,
  isConnected = false,
  onSelect,
}) => {
  return (
    <div
      className={cn(
        "flex items-center justify-between p-3.5 rounded-lg border transition-all duration-200",
        isConnected
          ? "border-emerald-800/60 bg-emerald-950/15"
          : "border-[#1a2a3a] bg-[#070d1a] hover:border-cyan-500/40"
      )}
    >
      <div className="space-y-1.5 min-w-0 pr-3">
        <div className="flex items-center gap-2 flex-wrap">
          <CodeBadge variant={isConnected ? "success" : isProposer ? "active" : "default"}>
            Dev #{devIndex + 1}
          </CodeBadge>

          {isProposer ? (
            <StatusPill color="cyan" label="Proposer (Deployer)" />
          ) : (
            <StatusPill color="emerald" label="Threshold Approver" />
          )}

          {isConnected && (
            <StatusPill color="emerald" label="Active Signer" dot />
          )}
        </div>

        <div className="text-slate-400 font-mono text-[11px] truncate select-all">
          {address}
        </div>
      </div>

      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-sans font-medium transition-all",
          isConnected
            ? "border border-emerald-700/50 bg-emerald-950/40 text-emerald-300"
            : "border border-cyan-500/50 bg-cyan-950/40 hover:bg-cyan-900/60 text-cyan-300 cursor-pointer"
        )}
      >
        {isConnected ? (
          <>
            <UserCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Connected</span>
          </>
        ) : (
          <>
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Connect Dev #{devIndex + 1}</span>
          </>
        )}
      </button>
    </div>
  );
};
