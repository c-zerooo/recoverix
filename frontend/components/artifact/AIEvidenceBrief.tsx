"use client";

import { useState } from "react";
import { Artifact, AIExplanation } from "@/lib/types";
import { fetchArtifactExplanation } from "@/lib/api";
import { BrainCircuit, RefreshCw, Zap } from "lucide-react";

export function AIEvidenceBrief({ artifact, initialBrief }: { artifact: Artifact, initialBrief: AIExplanation | null }) {
  const [brief, setBrief] = useState<AIExplanation | null>(initialBrief);
  const [loading, setLoading] = useState(false);

  const refreshBrief = async () => {
    setLoading(true);
    try {
      const freshBrief = await fetchArtifactExplanation(artifact.id);
      setBrief(freshBrief);
    } catch (err) {
      console.error("Failed to refresh AI brief", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <BrainCircuit className="w-6 h-6 text-cyan-400" />
          <h2 className="text-xl font-semibold text-slate-100">AI Evidence Brief</h2>
        </div>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1.5 px-2.5 py-1 bg-cyan-950/30 text-cyan-400 text-xs font-medium border border-cyan-500/20 rounded-lg">
            <Zap className="w-3.5 h-3.5" /> Grounded in Deterministic Facts • Pre-Warmed Cache
          </span>
          <button 
            onClick={refreshBrief}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
            {loading ? 'Refreshing...' : 'Verify / Refresh'}
          </button>
        </div>
      </div>

      {brief ? (
        <div className="space-y-6">
          <div className="bg-slate-950 p-4 rounded-lg border border-slate-800">
            <h3 className="text-sm font-semibold text-slate-400 mb-2 uppercase tracking-wider">Executive Summary</h3>
            <p className="text-slate-200">{brief.summary}</p>
          </div>
          
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Detailed Grounded Analysis</h3>
            <ul className="space-y-3">
              {brief.details.map((detail, idx) => (
                <li key={idx} className="flex items-start gap-3 text-sm text-slate-300">
                  <div className="w-1.5 h-1.5 rounded-full bg-cyan-500 mt-1.5 shrink-0" />
                  <span>{detail}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : (
        <div className="text-center py-8 text-slate-500 italic">
          No AI Brief available for this artifact.
        </div>
      )}
    </div>
  );
}
