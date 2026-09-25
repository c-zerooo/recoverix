"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { fetchCase, fetchArtifacts } from "@/lib/api";
import { ArtifactTable } from "@/components/dashboard/ArtifactTable";
import { Loader2, UploadCloud } from "lucide-react";
import { Case, Artifact } from "@/lib/types";

export default function DashboardPage() {
  const searchParams = useSearchParams();
  const [data, setData] = useState<{ caseData: Case | null; artifacts: Artifact[] }>({ caseData: null, artifacts: [] });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      setIsLoading(true);
      const urlId = searchParams.get('case_id');
      const localId = typeof window !== 'undefined' ? localStorage.getItem('recoverix_active_case_id') : null;
      const activeCaseId = urlId || localId;
      
      if (!activeCaseId) {
        setIsLoading(false);
        return;
      }

      try {
        const [c, a] = await Promise.all([
          fetchCase(activeCaseId),
          fetchArtifacts(activeCaseId)
        ]);

        const hasLegacyArtifacts = a.some((art: Artifact) => 
          ['fragmented_contacts.csv', 'corrupted.png', 'ledger.csv', 'auth_trace.txt'].includes(art.filename)
        );

        if (hasLegacyArtifacts && typeof window !== 'undefined') {
          localStorage.removeItem('recoverix_active_case_id');
          for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && key.startsWith('recoverix_artifacts_')) {
              localStorage.removeItem(key);
            }
          }
          setData({ caseData: null, artifacts: [] });
          setIsLoading(false);
          return;
        }
        
        if (typeof window !== 'undefined') {
          localStorage.setItem(`recoverix_artifacts_${activeCaseId}`, JSON.stringify(a));
        }
        
        setData({ caseData: c, artifacts: a });
      } catch (err) {
        // Fallback to empty if case not found
        setData({ caseData: null, artifacts: [] });
      } finally {
        setIsLoading(false);
      }
    }
    loadData();
  }, [searchParams]);

  if (isLoading) {
    return (
      <main className="min-h-screen bg-[#0B0F1A] flex items-center justify-center">
        <Loader2 className="w-12 h-12 text-pink-500 animate-spin" />
      </main>
    );
  }

  const { caseData, artifacts } = data;
  
  const totalArts = artifacts.length;
  const fullyRec = artifacts.filter(a => a.status === 'FULLY_RECOVERED').length;
  const partialRec = artifacts.filter(a => a.status === 'PARTIALLY_RECOVERED' || a.status === 'CORRUPTED').length;
  const highCrit = artifacts.filter(a => a.priority === 'HIGH' || a.priority === 'CRITICAL').length;

  return (
    <main className="min-h-screen bg-[#0B0F1A] text-slate-200 py-8 px-6">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Compact Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <Link href="/" className="inline-flex items-center text-sm text-slate-400 hover:text-slate-200 transition-colors bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.08] px-3 py-1.5 rounded-lg">
              <UploadCloud className="w-4 h-4 mr-2" /> Upload New File
            </Link>
            <h1 className="text-2xl font-semibold tracking-tight text-white border-l border-[#1E293B] pl-4">
              Case Results
            </h1>
          </div>
          
          <button 
            onClick={() => {
              if (!caseData) return;
              const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(data, null, 2));
              const anchor = document.createElement('a');
              anchor.href = dataStr;
              anchor.download = `recoverix_report_${caseData.id}.json`;
              anchor.click();
            }}
            disabled={!caseData}
            className="bg-white/[0.06] hover:bg-white/[0.1] border border-white/[0.1] text-white text-xs font-medium px-3.5 py-2 rounded-lg transition-colors disabled:opacity-50"
          >
            Export JSON
          </button>
        </div>

        {/* 4-column Stat Strip */}
        <div className="bg-[#111622] border border-white/[0.08] rounded-xl p-4 grid grid-cols-2 md:grid-cols-4 divide-x divide-white/[0.08]">
          <div className="px-4">
            <div className="flex items-center gap-1.5 mb-1">
              <div className="w-2 h-2 rounded-full bg-slate-500" />
              <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">Total Artifacts</span>
            </div>
            <p className="text-2xl font-semibold text-white">{totalArts}</p>
          </div>
          <div className="px-4">
            <div className="flex items-center gap-1.5 mb-1">
              <div className="w-2 h-2 rounded-full bg-sky-400" />
              <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">Fully Recovered</span>
            </div>
            <p className="text-2xl font-semibold text-white">{fullyRec}</p>
          </div>
          <div className="px-4">
            <div className="flex items-center gap-1.5 mb-1">
              <div className="w-2 h-2 rounded-full bg-pink-400" />
              <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">Partial / Corrupted</span>
            </div>
            <p className="text-2xl font-semibold text-white">{partialRec}</p>
          </div>
          <div className="px-4">
            <div className="flex items-center gap-1.5 mb-1">
              <div className="w-2 h-2 rounded-full bg-rose-500" />
              <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">High / Critical</span>
            </div>
            <p className="text-2xl font-semibold text-white">{highCrit}</p>
          </div>
        </div>

        {/* Artifacts Table */}
        <ArtifactTable artifacts={artifacts} />
      </div>
    </main>
  );
}
