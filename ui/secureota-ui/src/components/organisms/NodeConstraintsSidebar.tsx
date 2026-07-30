import * as React from "react";
import { Cpu, CloudUpload, Hash, AlertTriangle, CheckCircle2 } from "lucide-react";
import { CodeBadge } from "../atoms/CodeBadge";
import { DropZone } from "../molecules/DropZone";
import { ResourceMetricMeter } from "../molecules/ResourceMatrix";

export interface NodeConstraintsSidebarProps {
  firmwareVersion: string;
  ramFreeKb: number;
  ramTotalKb: number;
  otaUsedKb: number;
  otaTotalKb: number;
  baseUploaded: boolean;
  targetUploaded: boolean;
  deltaGenerated: boolean;
  goldenHash: string | null;
  deltaSizeKb: number | null;
  compressionRatio: string | null;
  onUploadBase: () => void;
  onUploadTarget: () => void;
}

export const NodeConstraintsSidebar: React.FC<NodeConstraintsSidebarProps> = ({
  firmwareVersion,
  ramFreeKb,
  ramTotalKb,
  otaUsedKb,
  otaTotalKb,
  baseUploaded,
  targetUploaded,
  deltaGenerated,
  goldenHash,
  deltaSizeKb,
  compressionRatio,
  onUploadBase,
  onUploadTarget,
}) => {
  const binariesLoaded = baseUploaded && targetUploaded;
  const ramUsedKb = ramTotalKb - ramFreeKb;
  const ramPercentage = Math.round((ramUsedKb / ramTotalKb) * 100);
  const otaPercentage = Math.round((otaUsedKb / otaTotalKb) * 100);

  return (
    <aside className="border-r border-[#1a2a3a] bg-[#060c18] flex flex-col overflow-y-auto w-[380px] shrink-0">
      <section className="p-5 border-b border-[#1a2a3a]">
        <div className="flex items-center gap-2.5">
          <Cpu className="w-4 h-4 text-cyan-400" />
          <span className="text-xs uppercase tracking-wider text-cyan-400 font-sans font-semibold">
            Target Node Constraints
          </span>
        </div>

        <div className="mt-4 rounded-lg border border-[#1a2a3a] bg-[#070d1a] p-5 space-y-5">
          <div className="flex items-center justify-between">
            <span className="text-base text-white font-medium">ESP32 Target Node</span>
            <CodeBadge variant="default">{firmwareVersion}</CodeBadge>
          </div>

          <ResourceMetricMeter
            title="RAM Availability"
            currentValueText={`${ramFreeKb} KB Free`}
            usedText={`${ramUsedKb} KB used`}
            totalText={`${ramTotalKb / 1024} MB total`}
            statusLabel={ramPercentage > 80 ? "CRITICALLY LOW" : "NOMINAL"}
            percentage={ramPercentage}
            color={ramPercentage > 80 ? "rose" : "cyan"}
          />

          <ResourceMetricMeter
            title="OTA Partition Storage"
            currentValueText={`${(otaTotalKb / 1024).toFixed(1)} MB Limited`}
            usedText={`${otaUsedKb} KB used`}
            totalText={`${(otaTotalKb / 1024).toFixed(1)} MB total`}
            statusLabel={otaPercentage > 75 ? "LIMITED" : "NOMINAL"}
            percentage={otaPercentage}
            color={otaPercentage > 75 ? "amber" : "cyan"}
          />

          <div className="grid grid-cols-2 gap-2 pt-2">
            {[
              { label: "CPU", value: "240 MHz" },
              { label: "Cores", value: "2 x LX6" },
              { label: "Flash", value: "4 MB SPI" },
              { label: "Protocol", value: "CoAP/UDP" },
            ].map((item) => (
              <div key={item.label} className="bg-[#0a1525] rounded p-3 border border-[#1a2a3a]">
                <div className="text-[10px] text-slate-500 uppercase tracking-wider font-sans">
                  {item.label}
                </div>
                <div className="text-xs text-slate-300 mt-1 font-mono">{item.value}</div>
              </div>
            ))}
          </div>

          <div className="flex gap-3 p-3 bg-rose-950/20 rounded border border-rose-900/30">
            <AlertTriangle className="w-4 h-4 text-rose-500 shrink-0 mt-0.5" />
            <p className="text-xs text-rose-300/80 leading-relaxed font-sans">
              <strong className="text-rose-400">Problem:</strong> Standard monolithic firmware (~1.2 MB) risks memory exhaustion and OTA partition overflow on constrained hardware.
            </p>
          </div>
        </div>
      </section>

      <section className="p-5 border-b border-[#1a2a3a]">
        <div className="flex items-center gap-2.5">
          <CloudUpload className="w-4 h-4 text-violet-400" />
          <span className="text-xs uppercase tracking-wider text-violet-400 font-sans font-semibold">
            Firmware Upload Pipeline
          </span>
        </div>

        <div className="mt-4 space-y-3">
          <DropZone
            label="Upload Base Binary (v1.0)"
            filename="base_v1.0.bin"
            filesize="1.2 MB"
            isUploaded={baseUploaded}
            onUpload={onUploadBase}
          />
          <DropZone
            label="Upload Target Binary (v1.1)"
            filename="update_v1.1.bin"
            filesize="1.25 MB"
            isUploaded={targetUploaded}
            onUpload={onUploadTarget}
          />

          {binariesLoaded && (
            <div className="flex items-center gap-2 px-3 py-2 rounded bg-emerald-950/20 border border-emerald-900/30 font-sans">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
              <span className="text-xs text-emerald-400">
                Both binaries staged — ready for delta generation
              </span>
            </div>
          )}
        </div>
      </section>

      <section className="p-5 flex-1">
        <div className="flex items-center gap-2.5">
          <Hash className="w-4 h-4 text-emerald-400" />
          <span className="text-xs uppercase tracking-wider text-emerald-400 font-sans font-semibold">
            Patch Generation Metrics
          </span>
        </div>

        <div className="mt-4 rounded-lg border border-[#1a2a3a] bg-[#070d1a] p-5 space-y-3 font-mono">
          {[
            { label: "Base Binary (v1.0)", value: "1.200 MB", accent: "text-slate-300" },
            { label: "Target Binary (v1.1)", value: "1.250 MB", accent: "text-slate-300" },
            {
              label: "Generated Delta Patch",
              value: deltaGenerated && deltaSizeKb ? `${deltaSizeKb}.0 KB` : "Pending...",
              accent: deltaGenerated ? "text-cyan-400" : "text-slate-600",
            },
            {
              label: "Compression Ratio",
              value: deltaGenerated && compressionRatio ? compressionRatio : "Pending...",
              accent: deltaGenerated ? "text-emerald-400" : "text-slate-600",
            },
          ].map((row, i) => (
            <div
              key={row.label}
              className={`flex justify-between items-center py-2 ${
                i < 3 ? "border-b border-[#1a2a3a]" : ""
              }`}
            >
              <span className="text-xs text-slate-500 font-sans">{row.label}</span>
              <span className={`text-xs ${row.accent}`}>{row.value}</span>
            </div>
          ))}

          <div className="pt-3">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-2 font-sans">
              SHA-256 Golden Hash
            </div>
            <div className="p-3 bg-emerald-950/20 rounded border border-emerald-900/30 text-xs text-emerald-400 break-all leading-relaxed tracking-wide font-mono select-all">
              {goldenHash || "0x0000000000000000000000000000000000000000000000000000000000000000"}
            </div>
          </div>
        </div>
      </section>
    </aside>
  );
};
