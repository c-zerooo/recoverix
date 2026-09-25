"use client";

import { useState } from "react";
import Link from "next/link";
import { Artifact, PriorityLevel, ArtifactCategory } from "@/lib/types";
import { PriorityBadge, StatusBadge } from "./PriorityBadge";
import { Search, Filter, ChevronRight, File } from "lucide-react";

export function ArtifactTable({ artifacts }: { artifacts: Artifact[] }) {
  const [filterPriority, setFilterPriority] = useState<PriorityLevel | "ALL">("ALL");
  const [filterCategory, setFilterCategory] = useState<ArtifactCategory | "ALL">("ALL");
  const [search, setSearch] = useState("");

  const filtered = artifacts.filter(a => {
    if (filterPriority !== "ALL" && a.priority !== filterPriority) return false;
    if (filterCategory !== "ALL" && a.category !== filterCategory) return false;
    if (search && !a.filename.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
      {/* Table Toolbar */}
      <div className="p-4 border-b border-slate-800 flex flex-col sm:flex-row gap-4 justify-between items-center bg-slate-900/50">
        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input 
            type="text" 
            placeholder="Search filename..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-4 py-2 text-sm text-slate-200 focus:outline-none focus:border-cyan-500"
          />
        </div>
        <div className="flex gap-4 w-full sm:w-auto">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-500" />
            <select 
              value={filterPriority}
              onChange={(e) => setFilterPriority(e.target.value as any)}
              className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-cyan-500"
            >
              <option value="ALL">All Priorities</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>
          <select 
            value={filterCategory}
            onChange={(e) => setFilterCategory(e.target.value as any)}
            className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-cyan-500"
          >
            <option value="ALL">All Categories</option>
            <option value="DOCUMENT">Document</option>
            <option value="DATABASE_LOG">Database Log</option>
            <option value="PHOTO_MEDIA">Photo Media</option>
            <option value="SYSTEM_TRACE">System Trace</option>
            <option value="BINARY_ARCHIVE">Binary Archive</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-950 text-slate-400">
            <tr>
              <th className="px-6 py-4 font-medium">Artifact</th>
              <th className="px-6 py-4 font-medium">Priority / Status</th>
              <th className="px-6 py-4 font-medium">Confidence</th>
              <th className="px-6 py-4 font-medium">Provenance (Bytes)</th>
              <th className="px-6 py-4 font-medium">Validation</th>
              <th className="px-6 py-4 font-medium">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50">
            {filtered.map(artifact => (
              <tr key={artifact.id} className="hover:bg-slate-800/20 transition-colors">
                <td className="px-6 py-4">
                  <div className="flex items-start gap-3">
                    <File className="w-5 h-5 text-slate-500 mt-0.5 shrink-0" />
                    <div>
                      <p className="font-medium text-slate-200">{artifact.filename}</p>
                      <p className="text-xs text-slate-500 mt-1">
                        {artifact.category} • {artifact.mime_type}
                      </p>
                      <p className="text-xs text-cyan-500 mt-1 font-mono">
                        {artifact.reconstruction_method}
                      </p>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <div className="flex flex-col gap-2 items-start">
                    <PriorityBadge priority={artifact.priority} />
                    <StatusBadge status={artifact.status} />
                  </div>
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-medium text-slate-300 w-8">{artifact.confidence_score}%</span>
                    <div className="w-24 h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div 
                        className={`h-full rounded-full ${
                          artifact.confidence_score > 80 ? 'bg-emerald-500' :
                          artifact.confidence_score > 50 ? 'bg-amber-500' : 'bg-red-500'
                        }`}
                        style={{ width: `${artifact.confidence_score}%` }}
                      />
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4 font-mono text-xs">
                  <div className="flex items-center gap-1.5 px-2 py-1 bg-slate-950 border border-slate-800 rounded-md w-fit">
                    <span className="text-emerald-400" title="Verified Bytes">{artifact.verified_bytes}</span>
                    <span className="text-slate-700">/</span>
                    <span className="text-amber-400" title="Reconstructed Gap">{artifact.reconstructed_bytes}</span>
                    <span className="text-slate-700">/</span>
                    <span className="text-rose-400" title="Missing Bytes">{artifact.missing_bytes}</span>
                  </div>
                </td>
                <td className="px-6 py-4">
                  {artifact.validation.valid ? (
                    <span className="text-emerald-400 text-xs font-medium bg-emerald-500/10 px-2 py-1 rounded border border-emerald-500/20">PASSED</span>
                  ) : (
                    <div className="flex flex-col gap-1">
                      <span className="text-red-400 text-xs font-medium bg-red-500/10 px-2 py-1 rounded border border-red-500/20 inline-block w-fit">FAILED</span>
                      <span className="text-xs text-slate-500 truncate max-w-[150px]" title={artifact.validation.error}>
                        {artifact.validation.error}
                      </span>
                    </div>
                  )}
                </td>
                <td className="px-6 py-4">
                  <Link 
                    href={`/artifacts/${artifact.id}`}
                    className="inline-flex items-center gap-1 text-sm font-medium text-cyan-400 hover:text-cyan-300 transition-colors"
                  >
                    Inspect <ChevronRight className="w-4 h-4" />
                  </Link>
                </td>
              </tr>
            ))}
            
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-slate-500">
                  No artifacts match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
