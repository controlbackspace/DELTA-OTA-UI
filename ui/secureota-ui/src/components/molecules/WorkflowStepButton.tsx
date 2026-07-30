import * as React from "react";
import { CheckCircle2, ChevronRight } from "lucide-react";
import { cn } from "../../lib/utils";
import { CodeBadge } from "../atoms/CodeBadge";

export interface WorkflowStepButtonProps {
  stepNumber: number;
  label: string;
  subLabel: string;
  icon: React.ReactNode;
  isActive?: boolean;
  isLoading?: boolean;
  isCompleted?: boolean;
  isDisabled?: boolean;
  isLast?: boolean;
  onClick?: () => void;
}

export const WorkflowStepButton: React.FC<WorkflowStepButtonProps> = ({
  stepNumber,
  label,
  subLabel,
  icon,
  isActive = false,
  isLoading = false,
  isCompleted = false,
  isDisabled = false,
  isLast = false,
  onClick,
}) => {
  return (
    <div className="flex items-center flex-1 min-w-0">
      <button
        type="button"
        onClick={onClick}
        disabled={isDisabled || isLoading || isCompleted}
        className={cn(
          "relative flex-1 min-w-0 p-4 rounded-lg border transition-all duration-200 flex flex-col items-center gap-2.5 text-center select-none outline-none",
          isCompleted && "border-emerald-800/50 bg-emerald-950/15 text-emerald-400",
          isActive && !isCompleted && !isLoading && "border-cyan-700/60 bg-cyan-950/20 text-cyan-300 hover:border-cyan-500 hover:bg-cyan-950/30 cursor-pointer",
          isDisabled && !isCompleted && "border-[#1a2a3a] bg-[#070d1a]/50 text-slate-700 cursor-not-allowed"
        )}
      >
        {isLoading && (
          <div className="absolute inset-0 rounded-lg animate-pulse bg-cyan-400/10 border border-cyan-500/50" />
        )}

        <div className="relative z-10 flex items-center gap-2">
          <CodeBadge variant={isCompleted ? "success" : isActive ? "active" : "default"}>
            {stepNumber}
          </CodeBadge>
          {isCompleted ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          ) : (
            <span className={cn("shrink-0", isActive ? "text-cyan-400" : "text-slate-600")}>
              {icon}
            </span>
          )}
        </div>

        <div className="relative z-10 min-w-0 w-full">
          <div className="text-xs leading-tight truncate px-1 font-sans font-semibold">
            {label}
          </div>
          <div className="text-[10px] text-slate-500 mt-1 truncate">{subLabel}</div>
        </div>
      </button>

      {!isLast && (
        <ChevronRight className="w-4 h-4 text-slate-800 shrink-0 mx-1" />
      )}
    </div>
  );
};
