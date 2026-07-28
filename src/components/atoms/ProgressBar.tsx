import * as React from "react";
import { cn } from "../../lib/utils";

export type BarColor = "cyan" | "emerald" | "amber" | "rose";

export interface ProgressBarProps {
  value: number;
  color?: BarColor;
  className?: string;
}

const fillColors: Record<BarColor, string> = {
  cyan: "bg-cyan-500",
  emerald: "bg-emerald-500",
  amber: "bg-amber-500",
  rose: "bg-rose-500",
};

export const ProgressBar: React.FC<ProgressBarProps> = ({
  value,
  color = "cyan",
  className,
}) => {
  const clampedValue = Math.min(100, Math.max(0, value));

  return (
    <div
      className={cn(
        "w-full bg-[#0d1a28] rounded-full h-2.5 overflow-hidden border border-[#1a2a3a]",
        className
      )}
    >
      <div
        className={cn("h-full rounded-full transition-all duration-500 ease-out", fillColors[color])}
        style={{ width: `${clampedValue}%` }}
      />
    </div>
  );
};
