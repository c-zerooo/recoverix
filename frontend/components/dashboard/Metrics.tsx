import { Artifact } from "@/lib/types";

export function Metrics({ artifacts }: { artifacts: Artifact[] }) {
  const total = artifacts.length;
  const recovered = artifacts.filter(a => a.status === "FULLY_RECOVERED").length;
  const partial = artifacts.filter(a => a.status === "PARTIALLY_RECOVERED").length;
  const highPriority = artifacts.filter(a => a.priority === "CRITICAL" || a.priority === "HIGH").length;

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
      <div className="bg-[#131B2E] border border-[#1E293B] rounded-xl p-5">
        <p className="text-slate-400 text-sm font-medium mb-1">Total Artifacts</p>
        <p className="text-3xl font-bold text-sky-400">{total}</p>
      </div>

      <div className="bg-[#131B2E] border border-[#1E293B] rounded-xl p-5">
        <p className="text-slate-400 text-sm font-medium mb-1">Fully Recovered</p>
        <p className="text-3xl font-bold text-sky-400">{recovered}</p>
      </div>

      <div className="bg-[#131B2E] border border-[#1E293B] rounded-xl p-5">
        <p className="text-slate-400 text-sm font-medium mb-1">Partial Recovery</p>
        <p className="text-3xl font-bold text-pink-500">{partial}</p>
      </div>

      <div className="bg-[#131B2E] border border-[#1E293B] rounded-xl p-5">
        <p className="text-slate-400 text-sm font-medium mb-1">High / Critical Priority</p>
        <p className="text-3xl font-bold text-pink-500">{highPriority}</p>
      </div>
    </div>
  );
}
