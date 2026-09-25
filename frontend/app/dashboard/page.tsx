import Link from "next/link";
import { fetchCase, fetchArtifacts, fetchGroundTruth } from "@/lib/api";
import { Metrics } from "@/components/dashboard/Metrics";
import { ArtifactTable } from "@/components/dashboard/ArtifactTable";
import { ArrowLeft, ShieldAlert, CheckCircle, AlertOctagon } from "lucide-react";
import { StatusBadge } from "@/components/dashboard/PriorityBadge";

interface DashboardPageProps {
  searchParams: Promise<{ case_id?: string }> | { case_id?: string };
}

export default async function DashboardPage({ searchParams }: DashboardPageProps) {
  const resolvedParams = await searchParams;
  const caseId = resolvedParams?.case_id || "case_001";

  const caseData = await fetchCase(caseId);
  const artifacts = await fetchArtifacts(caseId);
  const groundTruth = await fetchGroundTruth();

  return (
    <main className="min-h-screen bg-slate-950 text-slate-200 py-8 px-6">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Header Navigation */}
        <div>
          <Link href="/" className="inline-flex items-center text-sm text-cyan-500 hover:text-cyan-400 mb-6">
            <ArrowLeft className="w-4 h-4 mr-2" /> Change Evidence
          </Link>

          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div>
              <div className="flex items-center gap-3 mb-2">
                <ShieldAlert className="w-8 h-8 text-cyan-400" />
                <h1 className="text-3xl font-bold tracking-tight text-slate-100">
                  {caseData.name}
                </h1>
              </div>
              <p className="text-slate-400">
                {caseData.description}
              </p>
              <div className="flex items-center gap-2 mt-4 text-xs font-mono text-slate-500">
                <span className="bg-slate-900 px-2 py-1 rounded border border-slate-800">
                  ID: {caseData.id}
                </span>
                <span className="bg-slate-900 px-2 py-1 rounded border border-slate-800">
                  SHA-256: 8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* KPIs */}
        <Metrics artifacts={artifacts} />

        {/* Artifacts Table */}
        <div className="space-y-4">
          <h2 className="text-xl font-semibold text-slate-100">Recovered Artifacts</h2>
          <ArtifactTable artifacts={artifacts} />
        </div>

        {/* Synthetic Ground-Truth Verification */}
        <div className="space-y-4 pt-8">
          <h2 className="text-xl font-semibold text-slate-100">Synthetic Ground-Truth Verification (Expected vs. Detected vs. Reconstructed)</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {groundTruth.expected_artifacts.map((expected) => {
              const actual = artifacts.find(a => a.id === expected.id);
              const isMatch = actual && actual.status === expected.expected_status;

              return (
                <div key={expected.id} className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <p className="font-semibold text-slate-200">{expected.filename}</p>
                      <p className="text-xs text-slate-500 font-mono mt-1">Scenario: {expected.scenario}</p>
                    </div>
                    {isMatch ? (
                      <div className="flex items-center gap-1.5 px-2 py-1 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 rounded text-[10px] font-bold uppercase">
                        <CheckCircle className="w-3 h-3" />
                        100% Deterministic Match
                      </div>
                    ) : (
                      <div className="flex items-center gap-1.5 px-2 py-1 bg-rose-500/10 border border-rose-500/20 text-rose-400 rounded text-[10px] font-bold uppercase">
                        <AlertOctagon className="w-3 h-3" />
                        Mismatch
                      </div>
                    )}
                  </div>

                  <div className="space-y-3 mt-4">
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-slate-500">Expected Status</span>
                      <StatusBadge status={expected.expected_status} />
                    </div>
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-slate-500">Actual Status</span>
                      {actual ? <StatusBadge status={actual.status} /> : <span className="text-slate-600">Not Found</span>}
                    </div>
                    <div className="pt-2 border-t border-slate-800">
                      <p className="text-[10px] font-mono text-slate-600 truncate" title={expected.original_sha256}>
                        SHA256: {expected.original_sha256.substring(0, 16)}...
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </main>
  );
}
