"use client";

import { useEffect, useState, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { fetchCase, fetchArtifacts } from "@/lib/api";
import { ArtifactTable } from "@/components/dashboard/ArtifactTable";
import { Loader2, UploadCloud } from "lucide-react";
import { Case, Artifact } from "@/lib/types";

function DashboardContent() {
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
      <main className="min-h-screen bg-[#F8FAFC] flex items-center justify-center">
        <Loader2 className="w-12 h-12 text-emerald-600 animate-spin" />
      </main>
    );
  }

  const { caseData, artifacts } = data;

  const totalArts = artifacts.length;
  const fullyRec = artifacts.filter(a => a.status === 'FULLY_RECOVERED').length;
  const partialRec = artifacts.filter(a => a.status === 'PARTIALLY_RECOVERED' || a.status === 'CORRUPTED').length;
  const highCrit = artifacts.filter(a => a.priority === 'HIGH' || a.priority === 'CRITICAL').length;

  return (
    <main className="min-h-screen bg-[#F8FAFC] text-slate-900 py-8 px-6 font-sans selection:bg-emerald-500/20 selection:text-emerald-950">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Compact Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            <Link href="/" className="inline-flex items-center text-xs font-mono text-slate-700 hover:text-slate-900 transition-colors bg-white hover:bg-slate-50 border border-slate-300 px-3.5 py-2 rounded-lg shadow-2xs font-semibold">
              <UploadCloud className="w-4 h-4 mr-2 text-emerald-600" /> Evidence Workspace
            </Link>
            <h1 className="text-xl font-bold font-mono tracking-tight text-slate-900 border-l border-slate-200 pl-4">
              CASE RESULTS & RECOVERED ARTIFACTS
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
            className="bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 text-xs font-mono px-3.5 py-2 rounded-lg transition-colors shadow-2xs disabled:opacity-50 font-semibold"
          >
            Export JSON Report
          </button>
        </div>

        {/* 4-column Stat Strip */}
        <div className="bg-white border border-slate-200 rounded-xl p-4 grid grid-cols-2 md:grid-cols-4 divide-x divide-slate-100 font-mono shadow-xs">
          <div className="px-4">
            <div className="flex items-center gap-1.5 mb-1">
              <div className="w-2 h-2 rounded-full bg-slate-400" />
              <span className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">Total Artifacts</span>
            </div>
            <p className="text-2xl font-bold text-slate-900">{totalArts}</p>
          </div>
          <div className="px-4">
            <div className="flex items-center gap-1.5 mb-1">
              <div className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="text-[10px] text-emerald-700 font-semibold uppercase tracking-wider">Fully Recovered</span>
            </div>
            <p className="text-2xl font-bold text-emerald-600">{fullyRec}</p>
          </div>
          <div className="px-4">
            <div className="flex items-center gap-1.5 mb-1">
              <div className="w-2 h-2 rounded-full bg-amber-500" />
              <span className="text-[10px] text-amber-700 font-semibold uppercase tracking-wider">Partial / Corrupted</span>
            </div>
            <p className="text-2xl font-bold text-amber-600">{partialRec}</p>
          </div>
          <div className="px-4">
            <div className="flex items-center gap-1.5 mb-1">
              <div className="w-2 h-2 rounded-full bg-rose-500" />
              <span className="text-[10px] text-rose-700 font-semibold uppercase tracking-wider">High / Critical</span>
            </div>
            <p className="text-2xl font-bold text-rose-600">{highCrit}</p>
          </div>
        </div>

        {/* Artifacts Table */}
        <ArtifactTable artifacts={artifacts} />
      </div>
    </main>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={
      <main className="min-h-screen bg-[#F8FAFC] flex items-center justify-center">
        <Loader2 className="w-12 h-12 text-emerald-600 animate-spin" />
      </main>
    }>
      <DashboardContent />
    </Suspense>
  );
}
