"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { fetchArtifactById, fetchArtifacts } from "@/lib/api";
import { ArrowLeft, FileText, File, Loader2 } from "lucide-react";
import { PriorityBadge, StatusBadge } from "@/components/dashboard/PriorityBadge";
import { ConfidenceBreakdown } from "@/components/artifact/ConfidenceBreakdown";
import { ProvenanceBar } from "@/components/artifact/ProvenanceBar";
import { ValidationResults } from "@/components/artifact/ValidationResults";
import { AIEvidenceBrief } from "@/components/artifact/AIEvidenceBrief";
import { Artifact } from "@/lib/types";

export default function ArtifactPage({ params }: { params: Promise<{ id: string }> }) {
  const resolvedParams = use(params);
  const artifactId = resolvedParams.id;
  const [data, setData] = useState<{ artifact: Artifact; relatedArtifacts: Artifact[] } | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    async function loadData() {
      try {
        const artifact = await fetchArtifactById(artifactId);
        
        const localCaseId = typeof window !== 'undefined' ? localStorage.getItem('recoverix_active_case_id') : null;
        const activeCaseId = localCaseId || 'case_001';
        
        const allArtifacts = await fetchArtifacts(activeCaseId);
        const relatedArtifacts = allArtifacts.filter(a => a.id !== artifact.id).slice(0, 3);
        
        setData({ artifact, relatedArtifacts });
      } catch (err) {
        console.error(err);
        setError(true);
      }
    }
    loadData();
  }, [artifactId]);

  if (error) {
    return (
      <main className="min-h-screen bg-slate-950 flex flex-col items-center justify-center text-slate-200">
        <h2 className="text-2xl font-bold mb-4">Artifact Not Found</h2>
        <Link href="/dashboard" className="text-cyan-500 hover:underline">Return to Dashboard</Link>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="min-h-screen bg-slate-950 flex items-center justify-center">
        <Loader2 className="w-12 h-12 text-cyan-400 animate-spin" />
      </main>
    );
  }

  const { artifact, relatedArtifacts } = data;

  return (
    <main className="min-h-screen bg-[#0B0F1A] text-slate-200 py-8 px-6">
      <div className="max-w-6xl mx-auto space-y-8">
        
        {/* Top Navigation & Header */}
        <div>
          <Link href="/dashboard" className="inline-flex items-center text-sm text-sky-400 hover:text-sky-300 mb-6 transition-colors">
            <ArrowLeft className="w-4 h-4 mr-2" /> Back to Dashboard
          </Link>

          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div>
              <div className="flex items-center gap-3 mb-3">
                <FileText className="w-8 h-8 text-white" />
                <h1 className="text-3xl font-bold tracking-tight text-white">
                  {artifact.filename}
                </h1>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-sm font-mono">
                <span className="bg-[#131B2E] px-2 py-1 rounded border border-[#1E293B] text-slate-400">
                  {artifact.mime_type}
                </span>
                <span className="bg-[#131B2E] px-2 py-1 rounded border border-[#1E293B] text-slate-400">
                  {artifact.category}
                </span>
                <PriorityBadge priority={artifact.priority} />
                <StatusBadge status={artifact.status} />
              </div>
            </div>
          </div>
        </div>

        {/* Layout Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <div className="space-y-8">
            <ProvenanceBar artifact={artifact} />
            <ConfidenceBreakdown artifact={artifact} />
            <ValidationResults artifact={artifact} />
          </div>
          <div className="space-y-8">
            {/* AI Brief */}
            <AIEvidenceBrief artifact={artifact} initialBrief={artifact.ai_summary} />
            
            {/* Recovered Byte Preview */}
            <div className="bg-[#131B2E] border border-[#1E293B] rounded-xl p-6">
              <h2 className="text-xl font-semibold text-white mb-4">File Preview</h2>
              <div className="bg-[#0B0F1A] border border-[#1E293B] rounded-lg p-4 overflow-x-auto">
                <pre className="text-sm font-mono text-slate-200 whitespace-pre-wrap break-all">
                  {artifact.preview_text}
                </pre>
              </div>
            </div>
          </div>
        </div>

        {/* Related Evidence */}
        {relatedArtifacts.length > 0 && (
          <div className="pt-8">
            <h2 className="text-lg font-semibold text-white mb-4">Related Evidence in Case</h2>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {relatedArtifacts.map(related => (
                <Link key={related.id} href={`/artifacts/${related.id}`} className="block">
                  <div className="bg-[#131B2E] border border-[#1E293B] hover:border-sky-400/50 rounded-xl p-4 transition-colors">
                    <div className="flex items-center gap-2 mb-2">
                      <File className="w-4 h-4 text-slate-500" />
                      <span className="font-medium text-white truncate">{related.filename}</span>
                    </div>
                    <div className="flex gap-2">
                      <StatusBadge status={related.status} />
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        )}

      </div>
    </main>
  );
}
