import * as React from "react";
import { X, Download, ShieldCheck, ShieldX, AlertTriangle, RefreshCw, FileDigit } from "lucide-react";
import { CodeBadge } from "../atoms/CodeBadge";
import { StatusPill } from "../atoms/StatusPill";
import { cn, formatFileSize } from "../../lib/utils";
import {
  PatchFetchError,
  compareToLedger,
  describeSource,
  failureText,
  fetchPatchBytes,
  formatHashShort,
  parsePatchUrl,
  type PatchFailure,
  type VerifyResult,
} from "../../features/governance/patchVerify";

export interface PatchDetailsDialogProps {
  version: string;
  /** Golden hash anchored on the ledger. */
  goldenHash: string;
  /** Patch address anchored on the ledger by the proposer. */
  patchUrl?: string;
  status: "Live" | "Pending" | "Revoked";
  onClose: () => void;
}

type Outcome =
  | { kind: "idle" }
  | { kind: "working"; step: "download" | "check" }
  | { kind: "match"; result: VerifyResult }
  | { kind: "mismatch"; result: VerifyResult }
  | { kind: "error"; failure: PatchFailure };

const statusColor = { Live: "emerald", Pending: "amber", Revoked: "rose" } as const;

export const PatchDetailsDialog: React.FC<PatchDetailsDialogProps> = ({ version, goldenHash, patchUrl, status, onClose }) => {
  const parsed = React.useMemo(() => parsePatchUrl(patchUrl), [patchUrl]);
  const [outcome, setOutcome] = React.useState<Outcome>({ kind: "idle" });
  const bytesRef = React.useRef<Uint8Array | null>(null);
  const busy = outcome.kind === "working";

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  /** Download once; later actions reuse the same bytes. */
  const load = async (): Promise<Uint8Array | null> => {
    if (!parsed.ok) {
      setOutcome({ kind: "error", failure: parsed.reason });
      return null;
    }
    if (bytesRef.current) return bytesRef.current;
    setOutcome({ kind: "working", step: "download" });
    try {
      bytesRef.current = await fetchPatchBytes(parsed.href);
      return bytesRef.current;
    } catch (err) {
      setOutcome({ kind: "error", failure: err instanceof PatchFetchError ? err.kind : "unreachable" });
      return null;
    }
  };

  const verify = async () => {
    const bytes = await load();
    if (!bytes) return;
    setOutcome({ kind: "working", step: "check" });
    const result = compareToLedger(bytes, goldenHash);
    setOutcome({ kind: result.match ? "match" : "mismatch", result });
  };

  const save = async () => {
    const bytes = await load();
    if (!bytes || !parsed.ok) return;
    const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: "application/octet-stream" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = parsed.fileName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    // Keep a verdict if there is one; otherwise show that the file arrived.
    setOutcome((prev) => (prev.kind === "working" ? { kind: "idle" } : prev));
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 font-sans"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div role="dialog" aria-label={`Patch details for ${version}`} className="w-full max-w-md rounded-xl border border-cyan-500/30 bg-[#070d18] shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[#1a2a3a] bg-[#05080f]">
          <div className="flex items-center gap-3">
            <CodeBadge variant={status === "Revoked" ? "danger" : status === "Live" ? "success" : "warning"}>{version}</CodeBadge>
            <span className="text-sm text-white font-medium">Delta patch</span>
            <StatusPill color={statusColor[status]} label={status} dot />
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/60 transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-5 py-5 space-y-4">
          <dl className="grid grid-cols-[88px_1fr] gap-x-3 gap-y-2.5 text-xs">
            <dt className="text-slate-500">File</dt>
            <dd className="text-slate-200 font-mono truncate" title={parsed.ok ? parsed.href : undefined}>
              {parsed.ok ? parsed.fileName : "Not available"}
            </dd>
            <dt className="text-slate-500">Hosted on</dt>
            <dd className="text-slate-200">
              {parsed.ok ? (
                <>
                  {describeSource(parsed.host)} <span className="text-slate-500 font-mono">({parsed.host})</span>
                </>
              ) : (
                "No download address on the ledger"
              )}
            </dd>
            <dt className="text-slate-500">Ledger hash</dt>
            <dd className="text-slate-200 font-mono select-all" title={goldenHash}>
              {formatHashShort(goldenHash)}
            </dd>
          </dl>

          <p className="text-xs text-slate-400 leading-relaxed">
            Check that the file at this address is exactly what the developers approved on the ledger.
          </p>

          {outcome.kind === "working" && (
            <div className="flex items-center gap-2.5 p-3 rounded-lg border border-cyan-800/40 bg-cyan-950/20 text-xs text-cyan-200">
              <RefreshCw className="w-4 h-4 animate-spin text-cyan-400 shrink-0" />
              {outcome.step === "download" ? "Downloading the patch..." : "Comparing with the ledger..."}
            </div>
          )}

          {outcome.kind === "match" && (
            <div className="p-3 rounded-lg border border-emerald-800/50 bg-emerald-950/20 space-y-1">
              <div className="flex items-center gap-2 text-sm text-emerald-300 font-medium">
                <ShieldCheck className="w-4 h-4 shrink-0" /> Matches the ledger
              </div>
              <p className="text-xs text-emerald-200/80">This file is exactly what was proposed. It is safe to approve.</p>
              <p className="text-[11px] text-slate-500 font-mono">
                {formatFileSize(outcome.result.size)} &middot; {formatHashShort(outcome.result.actual)}
              </p>
            </div>
          )}

          {outcome.kind === "mismatch" && (
            <div className="p-3 rounded-lg border border-rose-800/50 bg-rose-950/20 space-y-1.5">
              <div className="flex items-center gap-2 text-sm text-rose-300 font-medium">
                <ShieldX className="w-4 h-4 shrink-0" /> Does not match the ledger
              </div>
              <p className="text-xs text-rose-200/80">The file at this address is different from what was proposed. Do not approve this release.</p>
              <div className="text-[11px] text-slate-400 font-mono space-y-0.5">
                <div>Ledger: {formatHashShort(outcome.result.expected)}</div>
                <div>File: {formatHashShort(outcome.result.actual)}</div>
              </div>
            </div>
          )}

          {outcome.kind === "error" && (
            <div className="flex items-start gap-2.5 p-3 rounded-lg border border-amber-800/50 bg-amber-950/20 text-xs text-amber-200">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <span>{failureText(outcome.failure, parsed.ok ? parsed.host : "")}</span>
            </div>
          )}

          <div className="flex gap-2.5 pt-1">
            <button
              type="button"
              onClick={() => void verify()}
              disabled={busy || !parsed.ok}
              className={cn(
                "flex-1 inline-flex items-center justify-center gap-2 h-9 rounded-lg border text-xs font-medium transition-colors",
                "border-cyan-500/50 bg-cyan-950/40 text-cyan-300 hover:bg-cyan-900/40 disabled:opacity-40 disabled:cursor-not-allowed"
              )}
            >
              <FileDigit className="w-3.5 h-3.5" />
              Verify against ledger
            </button>
            <button
              type="button"
              onClick={() => void save()}
              disabled={busy || !parsed.ok}
              className="flex-1 inline-flex items-center justify-center gap-2 h-9 rounded-lg border border-slate-700 bg-slate-900/60 text-xs text-slate-200 hover:bg-slate-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Download className="w-3.5 h-3.5" />
              Download patch
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
