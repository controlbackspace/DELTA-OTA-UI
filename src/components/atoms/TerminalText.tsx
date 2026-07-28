import * as React from "react";
import { cn } from "../../lib/utils";

export type TerminalTextVariant = "info" | "success" | "warning" | "error" | "hash" | "timestamp";

export interface TerminalTextProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: TerminalTextVariant;
  children: React.ReactNode;
}

const variantStyles: Record<TerminalTextVariant, string> = {
  info: "text-slate-400",
  success: "text-emerald-400",
  warning: "text-amber-400",
  error: "text-rose-400",
  hash: "text-cyan-300 break-all",
  timestamp: "text-slate-600 select-none font-medium",
};

export const TerminalText: React.FC<TerminalTextProps> = ({
  variant = "info",
  children,
  className,
  ...props
}) => {
  return (
    <span
      className={cn("font-mono text-xs leading-relaxed", variantStyles[variant], className)}
      {...props}
    >
      {children}
    </span>
  );
};
