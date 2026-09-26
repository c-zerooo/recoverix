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
      const freshBrief = await fetchArtifactExplanation(artifact.id, true);
      setBrief(freshBrief);
    } catch (err) {
      console.error("Failed to refresh AI brief", err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white border border-slate-200/90 rounded-xl p-6 font-mono shadow-xs">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <BrainCircuit className="w-6 h-6 text-emerald-600" />
          <h2 className="text-xl font-bold text-slate-900">Forensic Evidence Brief</h2>
        </div>
        <div className="flex items-center gap-3">
          <span className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold border rounded-lg ${
            brief?.cached 
              ? 'bg-slate-100 text-slate-700 border-slate-200' 
              : 'bg-emerald-50 text-emerald-800 border-emerald-300'
          }`}>
            <Zap className="w-3.5 h-3.5" /> 
            {brief?.cached ? 'CACHED BRIEF' : 'GROUNDED ANALYSIS'}
          </span>
          <button 
            onClick={refreshBrief}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-1 bg-white hover:bg-slate-50 text-slate-700 border border-slate-300 text-xs rounded-lg transition-colors shadow-2xs font-semibold disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin text-emerald-600' : ''}`} />
            {loading ? 'Regenerating...' : 'Refresh'}
          </button>
        </div>
      </div>

      {brief ? (
        <div className="space-y-6">
          <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
            <h3 className="text-xs font-bold text-slate-500 mb-2 uppercase tracking-wider">Executive Summary</h3>
            <p className="text-slate-800 text-sm font-sans leading-relaxed">{brief.summary}</p>
          </div>
          
          <div className="space-y-4">
            <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider">Detailed Grounded Analysis</h3>
            <ul className="space-y-3 font-sans">
              {brief.details.map((detail, idx) => (
                <li key={idx} className="flex items-start gap-3 text-xs text-slate-700">
                  <div className="w-1.5 h-1.5 rounded-full bg-emerald-600 mt-1.5 shrink-0" />
                  <span className="leading-relaxed">{detail}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : (
        <div className="text-center py-8 text-slate-500 italic text-xs">
          No AI Brief available for this artifact.
        </div>
      )}
    </div>
  );
}
