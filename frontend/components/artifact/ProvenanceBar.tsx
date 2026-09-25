import { Artifact } from "@/lib/types";
import { ShieldCheck, Server, AlertOctagon } from "lucide-react";

export function ProvenanceBar({ artifact }: { artifact: Artifact }) {
  const totalExpected = artifact.verified_bytes + artifact.reconstructed_bytes + artifact.missing_bytes;
  
  const getPct = (val: number) => {
    if (totalExpected === 0) return 0;
    return (val / totalExpected) * 100;
  };

  const vPct = getPct(artifact.verified_bytes);
  const rPct = getPct(artifact.reconstructed_bytes);
  const mPct = getPct(artifact.missing_bytes);

  return (
    <div className="bg-[#131B2E] border border-[#1E293B] rounded-xl p-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-6 gap-4">
        <h2 className="text-xl font-semibold text-white">Byte Summary</h2>
        <div className="flex gap-2">
          <span className="px-2.5 py-1 bg-[#0B0F1A] border border-[#1E293B] rounded-lg text-xs font-mono text-sky-400">
            {artifact.reconstruction_method}
          </span>
          <span className={`px-2.5 py-1 rounded-lg text-xs font-medium border ${artifact.validation.valid ? 'bg-sky-400/10 text-sky-400 border-sky-400/20' : 'bg-pink-500/10 text-pink-500 border-pink-500/20'}`}>
            {artifact.validation.valid ? 'VALIDATION PASSED' : 'VALIDATION FAILED'}
          </span>
        </div>
      </div>

      <div className="w-full h-4 rounded-full overflow-hidden flex mb-6 bg-[#0B0F1A] border border-[#1E293B]">
        <div style={{ width: `${vPct}%` }} className="h-full bg-sky-400" title={`Verified: ${vPct.toFixed(1)}%`} />
        <div style={{ width: `${rPct}%` }} className="h-full bg-pink-500" title={`Reconstructed: ${rPct.toFixed(1)}%`} />
        <div style={{ width: `${mPct}%` }} className="h-full bg-slate-500" title={`Missing: ${mPct.toFixed(1)}%`} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div className="bg-[#0B0F1A] p-4 rounded-lg border border-[#1E293B]">
          <div className="flex items-center gap-2 mb-2">
            <ShieldCheck className="w-4 h-4 text-sky-400" />
            <span className="text-sm font-medium text-slate-400">Verified Bytes</span>
          </div>
          <p className="text-2xl font-bold text-white font-mono">{artifact.verified_bytes}</p>
          <p className="text-xs text-sky-400 mt-1">{vPct.toFixed(1)}% of total</p>
        </div>
        <div className="bg-[#0B0F1A] p-4 rounded-lg border border-[#1E293B]">
          <div className="flex items-center gap-2 mb-2">
            <Server className="w-4 h-4 text-pink-500" />
            <span className="text-sm font-medium text-slate-400">Reconstructed Gap</span>
          </div>
          <p className="text-2xl font-bold text-white font-mono">{artifact.reconstructed_bytes}</p>
          <p className="text-xs text-pink-500 mt-1">{rPct.toFixed(1)}% of total</p>
        </div>
        <div className="bg-[#0B0F1A] p-4 rounded-lg border border-[#1E293B]">
          <div className="flex items-center gap-2 mb-2">
            <AlertOctagon className="w-4 h-4 text-slate-500" />
            <span className="text-sm font-medium text-slate-400">Missing Bytes</span>
          </div>
          <p className="text-2xl font-bold text-white font-mono">{artifact.missing_bytes}</p>
          <p className="text-xs text-slate-500 mt-1">{mPct.toFixed(1)}% of total</p>
        </div>
      </div>

      <div className="mb-6">
        <h3 className="text-sm font-semibold text-white mb-3">Fragment Map</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#0B0F1A] text-slate-400">
              <tr>
                <th className="px-4 py-2 font-medium">Fragment ID</th>
                <th className="px-4 py-2 font-medium">Offset</th>
                <th className="px-4 py-2 font-medium">Length</th>
                <th className="px-4 py-2 font-medium">Type</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1E293B] text-slate-300">
              {artifact.fragments.map(f => {
                const len = f.end_offset - f.start_offset;
                return (
                  <tr key={f.id} className="hover:bg-[#1E293B]/30 transition-colors">
                    <td className="px-4 py-2 font-mono text-xs">{f.id}</td>
                    <td className="px-4 py-2 font-mono text-xs">{f.start_offset} - {f.end_offset}</td>
                    <td className="px-4 py-2 font-mono text-xs">{len} bytes</td>
                    <td className="px-4 py-2">
                      <span className={`text-xs px-2 py-1 rounded font-medium ${
                        f.type === 'VERIFIED' ? 'bg-sky-400/10 text-sky-400' :
                        f.type === 'RECONSTRUCTED_GAP' ? 'bg-pink-500/10 text-pink-500' :
                        'bg-slate-500/10 text-slate-400'
                      }`}>
                        {f.type}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-[#0B0F1A] border border-[#1E293B] text-slate-400 rounded-lg p-4 text-sm text-center">
        <span className="font-semibold text-white">Zero AI Byte Fabrication:</span> AI never invents or infills missing evidence bytes.
      </div>
    </div>
  );
}
