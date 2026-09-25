import { Artifact } from "@/lib/types";
import { Database, CheckCircle, AlertTriangle, Flame } from "lucide-react";

export function Metrics({ artifacts }: { artifacts: Artifact[] }) {
  const total = artifacts.length;
  const recovered = artifacts.filter(a => a.status === "FULLY_RECOVERED").length;
  const partial = artifacts.filter(a => a.status === "PARTIALLY_RECOVERED").length;
  const highPriority = artifacts.filter(a => a.priority === "CRITICAL" || a.priority === "HIGH").length;

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 flex items-center">
        <div className="bg-slate-800 p-3 rounded-lg mr-4">
          <Database className="w-6 h-6 text-cyan-400" />
        </div>
        <div>
          <p className="text-sm text-slate-400 font-medium">Total Artifacts</p>
          <p className="text-2xl font-bold text-slate-100">{total}</p>
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 flex items-center">
        <div className="bg-emerald-950/50 p-3 rounded-lg mr-4">
          <CheckCircle className="w-6 h-6 text-emerald-400" />
        </div>
        <div>
          <p className="text-sm text-slate-400 font-medium">Fully Recovered</p>
          <p className="text-2xl font-bold text-slate-100">{recovered}</p>
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 flex items-center">
        <div className="bg-amber-950/50 p-3 rounded-lg mr-4">
          <AlertTriangle className="w-6 h-6 text-amber-400" />
        </div>
        <div>
          <p className="text-sm text-slate-400 font-medium">Partial Recovery</p>
          <p className="text-2xl font-bold text-slate-100">{partial}</p>
        </div>
      </div>

      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 flex items-center">
        <div className="bg-red-950/50 p-3 rounded-lg mr-4">
          <Flame className="w-6 h-6 text-red-400" />
        </div>
        <div>
          <p className="text-sm text-slate-400 font-medium">High/Critical Priority</p>
          <p className="text-2xl font-bold text-slate-100">{highPriority}</p>
        </div>
      </div>
    </div>
  );
}
