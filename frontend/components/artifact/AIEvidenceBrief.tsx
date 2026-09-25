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
    <div className="bg-[#131B2E] border border-[#1E293B] rounded-xl p-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-3">
          <BrainCircuit className="w-6 h-6 text-pink-500" />
          <h2 className="text-xl font-semibold text-white">AI Evidence Brief</h2>
        </div>
        <div className="flex items-center gap-3">
          <span className={`flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium border rounded-lg ${
            brief?.cached 
              ? 'bg-[#0B0F1A] text-slate-400 border-[#1E293B]' 
              : 'bg-sky-400/10 text-sky-400 border-sky-400/20'
          }`}>
            <Zap className="w-3.5 h-3.5" /> 
            {brief?.cached ? 'CACHED AI BRIEF' : 'REAL-TIME AI BRIEF'}
          </span>
          <button 
            onClick={refreshBrief}
            disabled={loading}
            className="flex items-center gap-2 px-3 py-1 bg-pink-500/15 hover:bg-pink-500/25 text-pink-400 text-xs rounded-lg transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin text-pink-500' : ''}`} />
            {loading ? 'Regenerating...' : 'Refresh'}
          </button>
        </div>
      </div>

      {brief ? (
        <div className="space-y-6">
          <div className="bg-[#0B0F1A] p-4 rounded-lg border border-[#1E293B]">
            <h3 className="text-sm font-semibold text-slate-400 mb-2 uppercase tracking-wider">Executive Summary</h3>
            <p className="text-slate-200">{brief.summary}</p>
          </div>
          
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Detailed Grounded Analysis</h3>
            <ul className="space-y-3">
              {brief.details.map((detail, idx) => (
                <li key={idx} className="flex items-start gap-3 text-sm text-slate-300">
                  <div className="w-1.5 h-1.5 rounded-full bg-pink-500 mt-1.5 shrink-0" />
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
