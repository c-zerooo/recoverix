import Link from "next/link";
import { fetchCase, fetchArtifacts } from "@/lib/api";
import { Metrics } from "@/components/dashboard/Metrics";
import { ArtifactTable } from "@/components/dashboard/ArtifactTable";
import { ArrowLeft, ShieldAlert } from "lucide-react";

export default async function DashboardPage() {
  const caseData = await fetchCase();
  const artifacts = await fetchArtifacts();

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
      </div>
    </main>
  );
}
