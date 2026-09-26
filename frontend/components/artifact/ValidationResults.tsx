import { Artifact } from "@/lib/types";
import { CheckCircle, XCircle, AlertTriangle } from "lucide-react";

export function ValidationResults({ artifact }: { artifact: Artifact }) {
  const { checks, error } = artifact.validation;

  return (
    <div className="bg-white border border-slate-200/90 rounded-xl p-6 font-mono shadow-xs">
      <h2 className="text-xl font-bold text-slate-900 mb-6">Structural Validation Audit</h2>
      
      {error && (
        <div className="bg-rose-50 border border-rose-300 text-rose-800 rounded-lg p-4 flex items-start gap-3 mb-6 text-xs">
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5 text-rose-600" />
          <div className="space-y-1">
            <span className="font-bold block uppercase tracking-wider text-rose-900">Defensive Bounds Checking</span>
            <p>The parser rejected malformed structure: <span className="font-mono text-slate-900 font-bold">{error}</span>.</p>
            <p className="opacity-80">This prevents crashes and ensures only deterministically verified bytes are promoted.</p>
          </div>
        </div>
      )}

      <div className="space-y-3">
        {checks && checks.length > 0 ? (
          checks.map((check, idx) => (
            <div key={idx} className="flex items-start gap-3 bg-slate-50 p-3 rounded-lg border border-slate-200 text-xs">
              {check.passed ? (
                <CheckCircle className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
              )}
              <div>
                <p className="font-bold text-slate-900">{check.name}</p>
                <p className="text-slate-600 mt-0.5">{check.detail}</p>
              </div>
            </div>
          ))
        ) : (
          <p className="text-slate-500 text-xs italic">No specific validation checks recorded.</p>
        )}
      </div>
    </div>
  );
}
