import * as React from "react";
import { Link2, Server, Cpu, CheckCircle2 } from "lucide-react";
import { ProgressBar } from "../atoms/ProgressBar";
import { StatusPill } from "../atoms/StatusPill";
import type { StatusColor } from "../atoms/StatusPill";
import type { UpdateState } from "../../features/firmware/useFirmwarePipeline";
import type { GatewayStatus } from "../../features/deployment/useGatewayStatus";
import type { LedgerRelease } from "./LedgerDeploymentsTable";

export interface DeploymentTrackerProps {
  version: string;
  stage: UpdateState;
  record: LedgerRelease | null;
  gatewayOnline: boolean;
  status: GatewayStatus | null;
  deviceBlock: number | null;
  /** Gateway machine's address when it is not this PC (e.g. the Raspberry Pi). */
  gatewayHost?: string;
  onGatewayHostChange?: (host: string) => void;
}

type StepState = "done" | "active" | "pending";

const ORDER: UpdateState[] = ["blockchain", "gateway", "iot", "success"];

const stepState = (stage: UpdateState, step: UpdateState): StepState => {
  const at = ORDER.indexOf(stage);
  const idx = ORDER.indexOf(step);
  if (stage === "success" || at > idx) return "done";
  return at === idx ? "active" : "pending";
};

const pill: Record<StepState, StatusColor> = { done: "emerald", active: "cyan", pending: "slate" };

const Step: React.FC<{
  icon: React.ReactNode;
  title: string;
  state: StepState;
  detail: string;
  children?: React.ReactNode;
}> = ({ icon, title, state, detail, children }) => (
  <div className="flex-1 min-w-0 p-3 rounded-lg border border-[#1a2a3a] bg-[#070d18] space-y-2">
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-2 text-xs text-slate-300 font-sans font-medium">
        {icon}
        {title}
      </span>
      <StatusPill
        color={pill[state]}
        label={state === "done" ? "Done" : state === "active" ? "In progress" : "Pending"}
        dot
      />
    </div>
    <p className="text-[11px] text-slate-400 font-sans leading-snug">{detail}</p>
    {children}
  </div>
);

/** Live chain → gateway → device view for the release being deployed. Every
 *  value shown comes from the chain record or gateway_status.json. */
export const DeploymentTracker: React.FC<DeploymentTrackerProps> = ({
  version,
  stage,
  record,
  gatewayOnline,
  status,
  deviceBlock,
  gatewayHost = "",
  onGatewayHostChange,
}) => {
  const total = status?.blocks_total ?? null;
  const pct = deviceBlock !== null && total ? (deviceBlock / total) * 100 : 0;

  const chainDetail = record?.isLive
    ? `${version} live on-chain (${record.approvalCount}/2 approvals).`
    : `${version}: ${record?.approvalCount ?? 0}/2 approvals — needs a second authorized signer.`;

  const gatewayDetail = !gatewayOnline
    ? "Status feed offline — start the gateway and the artifact server (:8000)."
    : status?.gateway_state === "staged" && status.staged_version === version
      ? `Verified + encrypted ${total ?? "?"} blocks (key fp ${status.key_fp ?? "?"}).`
      : `Gateway is "${status?.gateway_state ?? "unknown"}"${status?.target_version ? ` (following ${status.target_version})` : ""}.`;

  const deviceDetail =
    stage === "success"
      ? `Device ${status?.device_reported_ip ?? ""} reports ${version}.`
      : deviceBlock === null
        ? "Waiting for the device to request blocks."
        : status?.device_final_sent
          ? `All ${total} blocks delivered to ${status.device_ip ?? "device"} — committing + rebooting.`
          : `Device ${status?.device_ip ?? ""} pulling block ${deviceBlock}/${total ?? "?"}.`;

  return (
    <div className="shrink-0 px-6 py-4 border-b border-[#1a2a3a] bg-[#060c18]">
      {onGatewayHostChange && (
        <label className="flex items-center gap-2 mb-3 text-[11px] text-slate-400 font-sans">
          Gateway address
          <input
            value={gatewayHost}
            onChange={(e) => onGatewayHostChange(e.target.value)}
            spellCheck={false}
            className="flex-1 min-w-0 h-8 px-3 rounded border border-[#1a2a3a] bg-[#070d18] text-slate-200 font-mono text-[11px]"
          />
          <span className="text-slate-600">:8000</span>
        </label>
      )}
      <div className="flex items-stretch gap-3">
        <Step
          icon={<Link2 className="w-3.5 h-3.5 text-cyan-400" />}
          title="Chain"
          state={stepState(stage, "blockchain")}
          detail={chainDetail}
        />
        <Step
          icon={<Server className="w-3.5 h-3.5 text-cyan-400" />}
          title="Gateway"
          state={stepState(stage, "gateway")}
          detail={gatewayDetail}
        />
        <Step
          icon={<Cpu className="w-3.5 h-3.5 text-cyan-400" />}
          title="Device transfer"
          state={stepState(stage, "iot")}
          detail={deviceDetail}
        >
          {stage === "iot" && deviceBlock !== null && <ProgressBar value={pct} />}
        </Step>
        <Step
          icon={<CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}
          title="Running"
          state={stage === "success" ? "done" : "pending"}
          detail={
            stage === "success"
              ? `Confirmed: device booted ${version}.`
              : `Waiting for the device to report ${version} after reboot.`
          }
        />
      </div>
    </div>
  );
};
