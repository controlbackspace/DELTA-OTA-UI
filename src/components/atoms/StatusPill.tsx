import * as React from "react";
import { cn } from "../../lib/utils";

export type StatusColor = "cyan" | "emerald" | "amber" | "rose" | "slate";

export interface StatusPillProps extends React.HTMLAttributes<HTMLDivElement> {
  label: string;
  color?: StatusColor;
  dot?: boolean;
}

const colorStyles: Record<StatusColor, string> = {
  cyan: "border-cyan-800/50 bg-cyan-950/20 text-cyan-400",
  emerald: "border-emerald-800/50 bg-emerald-950/20 text-emerald-400",
  amber: "border-amber-800/50 bg-amber-950/20 text-amber-400",
  rose: "border-rose-800/50 bg-rose-950/20 text-rose-400",
  slate: "border-slate-800 bg-slate-900/30 text-slate-500",
}; 

const dotColors: Record<StatusColor, string> = {
  cyan: "bg-cyan-400",
  emerald: "bg-emerald-400",
  amber: "bg-amber-400",
  rose: "bg-rose-400",
  slate: "bg-slate-600",
};
export const StatusPill: React.FC<StatusPillProps> = ({
  label,
  color = "slate",
  dot = false,
  className,
  ...props
}) => {
  return (
    <div
      className={cn(
        "flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-sans font-medium select-none",
        colorStyles[color],
        className
      )}
      {...props}
    >
      {dot && (
        <span
          className={cn("w-2 h-2 rounded-full animate-pulse shrink-0", dotColors[color])}
        />
      )}
      <span>{label}</span>
    </div>
  );
};
