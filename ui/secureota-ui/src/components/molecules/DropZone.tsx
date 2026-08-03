import * as React from "react";
import { CloudUpload, CheckCircle2, FileUp } from "lucide-react";
import { cn } from "../../lib/utils";

export interface DropZoneProps {
  label: string;
  filename: string;
  filesize: string;
  isUploaded: boolean;
  onUpload: (file: File) => void;
}

export const DropZone: React.FC<DropZoneProps> = ({
  label,
  filename,
  filesize,
  isUploaded,
  onUpload,
}) => {
  const [isDragging, setIsDragging] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) onUpload(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) onUpload(file);
    e.target.value = "";
  };

  return (
    <div
      onDragOver={handleDragOver}
      onDragEnter={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={cn(
        "relative rounded-lg border-2 border-dashed transition-all duration-200 p-4",
        isDragging && "border-cyan-400/70 bg-cyan-950/25 scale-[1.01]",
        isUploaded && !isDragging && "border-emerald-800/50 bg-emerald-950/10",
        !isUploaded && !isDragging && "border-[#1e3040] bg-[#070d1a] hover:border-[#1e3a50]"
      )}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".bin"
        className="hidden"
        onChange={handleFileChange}
      />

      <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-3 font-sans font-medium">
        {label}
      </div>

      {isUploaded ? (
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded bg-emerald-900/25 border border-emerald-800/40 shrink-0">
            <FileUp className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs text-emerald-300 truncate font-mono">{filename}</div>
            <div className="flex items-center gap-2 mt-1">
              <CheckCircle2 className="w-3 h-3 text-emerald-500" />
              <span className="text-[10px] text-emerald-600 font-sans">{filesize} Verified</span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="text-[10px] text-slate-500 hover:text-slate-300 transition-colors shrink-0 px-2 py-1 rounded border border-transparent hover:border-[#1a2a3a] font-sans"
          >
            Replace
          </button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2.5 py-4">
          <CloudUpload className={cn("w-8 h-8 transition-colors", isDragging ? "text-cyan-400" : "text-slate-600")} />
          <div className="text-center font-sans">
            <div className="text-xs text-slate-500">
              Drag & drop <span className="text-slate-400 font-mono">.bin</span> file here
            </div>
            <div className="text-[10px] text-slate-600 mt-1">or</div>
          </div>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="text-[10px] px-3 py-1.5 rounded border border-[#1a2a3a] text-slate-400 hover:border-violet-700/50 hover:text-violet-300 transition-all font-sans"
          >
            Browse Files
          </button>
        </div>
      )}
    </div>
  );
};
