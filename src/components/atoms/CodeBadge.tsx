import * as React from "react";
import { cn } from "../../lib/utils";

export type CodeBadgeVariant = "default" | "active" | "success" | "warning" | "danger";

export interface CodeBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: CodeBadgeVariant;
  children: React.ReactNode;
}

const variantStyles: Record<CodeBadgeVariant, string> = {
  default: "bg-[#0d1a28] border-slate-700 text-slate-400",
  active: "bg-cyan-950/60 border-cyan-700/60 text-cyan-300",
  success: "bg-emerald-900/50 border-emerald-800 text-emerald-400",
  warning: "bg-amber-950/50 border-amber-800 text-amber-400",
  danger: "bg-rose-950/50 border-rose-800 text-rose-400",
};

export const CodeBadge: React.FC<CodeBadgeProps> = ({
  variant = "default",
  children,
  className,
  ...props
}) => {
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center px-2 py-0.5 rounded border text-xs font-mono font-semibold tracking-wide select-none",
        variantStyles[variant],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
};
