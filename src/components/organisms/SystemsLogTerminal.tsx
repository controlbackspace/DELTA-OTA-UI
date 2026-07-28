import * as React from "react";
import { Terminal, CheckCircle2 } from "lucide-react";
import { TerminalText } from "../atoms/TerminalText";
import type { TerminalTextVariant } from "../atoms/TerminalText";

export interface LogEntry {
  id: string | number;
  time: string;
  message: string;
  type: "info" | "success" | "warning" | "error" | "hash";
}

export interface SystemLogsTerminalProps {
  logs: LogEntry[];
  isProcessing?: boolean;
  isComplete?: boolean;
}

export const SystemLogsTerminal: React.FC<SystemLogsTerminalProps> = React.memo(({
  logs,
  isProcessing = false,
  isComplete = false,
}) => {
  const logsEndRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-black border-t border-[#1a2a3a]">
      <div className="shrink-0 flex items-center gap-4 px-6 py-3 bg-[#0a0f18] border-b border-[#1a2a3a]">
        <Terminal className="w-4 h-4 text-slate-600" />
        <span className="text-[10px] text-slate-500 uppercase tracking-wider font-sans font-medium">
          System Execution Logs
        </span>
        <span className="text-xs text-slate-700 font-mono">sepolia-testnet:11155111</span>

        <div className="ml-auto flex items-center gap-3 font-sans">
          {isProcessing && (
            <span className="flex items-center gap-2 text-xs text-cyan-400 animate-pulse">
              <span className="w-2 h-2 rounded-full bg-cyan-400" />
              Processing
            </span>
          )}
          {isComplete && (
            <span className="flex items-center gap-2 text-xs text-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Deployment Complete
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-2 font-mono text-xs">
        {logs.map((log) => (
          <div key={log.id} className="flex gap-4 leading-relaxed">
            <TerminalText variant="timestamp">[{log.time}]</TerminalText>
            <TerminalText variant={log.type as TerminalTextVariant}>
              {log.message}
            </TerminalText>
          </div>
        ))}
        <div ref={logsEndRef} />
      </div>
    </div>
  );
});

SystemLogsTerminal.displayName = "SystemLogsTerminal";
