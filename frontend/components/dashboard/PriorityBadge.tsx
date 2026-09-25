import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { PriorityLevel, RecoveryStatus } from "@/lib/types";

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function PriorityBadge({ priority }: { priority: PriorityLevel }) {
  const styles: Record<PriorityLevel, string> = {
    CRITICAL: "bg-pink-500/10 text-pink-500 border-pink-500/20",
    HIGH: "bg-pink-500/10 text-pink-500 border-pink-500/20",
    MEDIUM: "bg-sky-400/10 text-sky-400 border-sky-400/20",
    LOW: "bg-sky-400/10 text-sky-400 border-sky-400/20",
  };

  return (
    <span className={cn("px-2.5 py-0.5 rounded-md text-xs font-medium border", styles[priority])}>
      {priority}
    </span>
  );
}

export function StatusBadge({ status }: { status: RecoveryStatus }) {
  const styles: Record<RecoveryStatus, string> = {
    FULLY_RECOVERED: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    PARTIALLY_RECOVERED: "bg-amber-500/10 text-amber-400 border-amber-500/20",
    CORRUPTED: "bg-red-500/10 text-red-400 border-red-500/20",
    UNRECOVERABLE: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  };

  const labels: Record<RecoveryStatus, string> = {
    FULLY_RECOVERED: "FULLY RECOVERED",
    PARTIALLY_RECOVERED: "PARTIAL",
    CORRUPTED: "CORRUPTED",
    UNRECOVERABLE: "UNRECOVERABLE",
  };

  return (
    <span className={cn("px-2.5 py-0.5 rounded-md text-xs font-medium border", styles[status])}>
      {labels[status]}
    </span>
  );
}
