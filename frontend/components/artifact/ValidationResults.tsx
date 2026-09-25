import { Artifact } from "@/lib/types";
import { CheckCircle, XCircle, AlertTriangle } from "lucide-react";

export function ValidationResults({ artifact }: { artifact: Artifact }) {
  const { valid, checks, error } = artifact.validation;

  return (
    <div className="bg-[#131B2E] border border-[#1E293B] rounded-xl p-6">
      <h2 className="text-xl font-semibold text-white mb-6">Structural Validation</h2>
      
      {error && (
        <div className="bg-pink-500/10 border border-pink-500/30 text-pink-500 rounded-lg p-4 flex items-start gap-3 mb-6">
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5 text-pink-500" />
          <div className="text-sm">
            <span className="font-semibold block mb-1">Defensive Bounds Checking</span>
            <p>The parser rejected malformed structure: <span className="font-mono">{error}</span>.</p>
            <p className="mt-1 opacity-80">This prevents crashes and ensures only deterministically verified bytes are promoted.</p>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {checks && checks.length > 0 ? (
          checks.map((check, idx) => (
            <div key={idx} className="flex items-start gap-3 bg-[#0B0F1A] p-3 rounded-lg border border-[#1E293B]">
              {check.passed ? (
                <CheckCircle className="w-5 h-5 text-sky-400 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-5 h-5 text-pink-500 shrink-0 mt-0.5" />
              )}
              <div>
                <p className="font-medium text-slate-200 text-sm">{check.name}</p>
                <p className="text-slate-400 text-sm mt-0.5">{check.detail}</p>
              </div>
            </div>
          ))
        ) : (
          <p className="text-slate-500 text-sm italic">No specific validation checks recorded.</p>
        )}
      </div>
    </div>
  );
}
