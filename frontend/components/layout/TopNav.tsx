import Link from "next/link";
import { HardDrive } from "lucide-react";

export function TopNav() {
  return (
    <nav className="border-b border-slate-800 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-2 group">
            <HardDrive className="w-5 h-5 text-cyan-400 group-hover:text-cyan-300 transition-colors" />
            <span className="font-bold text-lg text-slate-100 tracking-tight">
              RECOVER<span className="text-cyan-400">IX</span>
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-2 px-3 py-1 bg-slate-900 border border-slate-800 rounded-full text-xs font-mono text-slate-400">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span>ENGINE READY</span>
            <span className="text-slate-600">•</span>
            <span>MAX_GAP: 4096B</span>
            <span className="text-slate-600">•</span>
            <span>MAX_IMAGE: 5MB</span>
          </div>
        </div>

        <div className="flex items-center gap-4 text-sm font-medium">
          <Link href="/" className="text-slate-400 hover:text-cyan-400 transition-colors">
            Upload Evidence
          </Link>
          <Link href="/dashboard" className="text-slate-400 hover:text-cyan-400 transition-colors">
            Investigator Dashboard
          </Link>
        </div>
      </div>
    </nav>
  );
}
