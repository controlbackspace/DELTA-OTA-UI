import * as React from "react";
import { ProgressBar } from "../atoms/ProgressBar";
import type { BarColor } from "../atoms/ProgressBar";
import { CodeBadge } from "../atoms/CodeBadge";

export interface ResourceMetricMeterProps {
  title: string;
  currentValueText: string;
  usedText: string;
  totalText: string;
  statusLabel: string;
  percentage: number;
  color?: BarColor;
}

export const ResourceMetricMeter: React.FC<ResourceMetricMeterProps> = ({
  title,
  currentValueText,
  usedText,
  totalText,
  statusLabel,
  percentage,
  color = "cyan",
}) => {
  return (
    <div className="space-y-2">
      <div className="flex justify-between text-sm">
        <span className="text-slate-500 font-sans">{title}</span>
        <span className="font-mono text-slate-200">{currentValueText}</span>
      </div>

      <ProgressBar value={percentage} color={color} />

      <div className="flex justify-between text-xs font-mono">
        <span className="text-slate-600">{usedText} / {totalText}</span>
        <CodeBadge variant={color === "rose" ? "danger" : color === "amber" ? "warning" : "active"}>
          {statusLabel}
        </CodeBadge>
      </div>
    </div>
  );
};
