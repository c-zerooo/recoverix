import { Artifact } from "@/lib/types";
import { StatusBadge } from "@/components/dashboard/PriorityBadge";
import { AlertTriangle } from "lucide-react";

export function ConfidenceBreakdown({ artifact }: { artifact: Artifact }) {
  const bd = artifact.confidence_breakdown;
  const metrics = [
    { label: "Header Validity", value: bd.header_validity, max: 20 },
    { label: "Footer / End Marker", value: bd.footer_validity, max: 20 },
    { label: "Structural Validation", value: bd.structural_validation, max: 30 },
    { label: "Size Plausibility", value: bd.size_plausibility, max: 15 },
    { label: "Reconstruction Integrity", value: bd.reconstruction_integrity, max: 15 },
  ];

  return (
    <div className="bg-[#131B2E] border border-[#1E293B] rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-white">Deterministic Confidence</h2>
          <p className="text-sm text-slate-400 mt-1">
            Overall Score: <span className="text-sky-400 font-bold text-lg">{artifact.confidence_score}/100</span>
          </p>
        </div>
        <StatusBadge status={artifact.status} />
      </div>

      <div className="space-y-4 mb-6">
        {metrics.map((m, idx) => {
          const pct = (m.value / m.max) * 100;
          return (
            <div key={idx}>
              <div className="flex justify-between text-sm mb-1 text-slate-300">
                <span>{m.label}</span>
                <span className="font-mono text-slate-400">{m.value} / {m.max} pts</span>
              </div>
              <div className="w-full h-2 bg-[#0B0F1A] border border-[#1E293B] rounded-full overflow-hidden">
                <div 
                  className={`h-full rounded-full ${pct >= 80 ? 'bg-sky-400' : 'bg-pink-500'}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="bg-[#0B0F1A] p-4 rounded-lg border border-[#1E293B] text-xs text-slate-400 font-mono flex flex-wrap gap-x-4 gap-y-2 mb-2">
        <span>85-100: FULLY_RECOVERED</span>
        <span>50-84: PARTIALLY_RECOVERED</span>
        <span>20-49: CORRUPTED</span>
        <span>0-19: UNRECOVERABLE</span>
      </div>
      <p className="text-xs text-slate-500 italic mb-4">
        Note: These status thresholds (85–100, 50–84, 20–49, 0–19) are our prototype policy, not an established forensic standard.
      </p>

      {artifact.reconstructed_bytes > 0 && (
        <div className="bg-pink-500/10 border border-pink-500/20 text-pink-500 rounded-lg p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
          <p className="text-sm">
            <span className="font-semibold block mb-1">Forensic Invariant Enforced</span>
            Because reconstructed_bytes &gt; 0, status is capped at PARTIALLY_RECOVERED and cannot be FULLY_RECOVERED.
          </p>
        </div>
      )}
    </div>
  );
}
