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
    <div className="bg-[#131B2E] border border-[#1E293B] rounded-xl overflow-hidden">
      {/* Table Toolbar */}
      <div className="p-4 border-b border-[#1E293B] flex flex-col sm:flex-row gap-4 justify-between items-center bg-[#131B2E]">
        <div className="relative w-full sm:w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input 
            type="text" 
            placeholder="Search filename..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full bg-[#0B0F1A] border border-[#1E293B] rounded-lg pl-9 pr-4 py-2 text-sm text-slate-200 focus:outline-none focus:border-pink-500"
          />
        </div>
        <div className="flex gap-4 w-full sm:w-auto">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-500" />
            <select 
              value={filterPriority}
              onChange={(e) => setFilterPriority(e.target.value as any)}
              className="bg-[#0B0F1A] border border-[#1E293B] rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-pink-500"
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
            className="bg-[#0B0F1A] border border-[#1E293B] rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-pink-500"
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
          <thead className="bg-[#0B0F1A] text-slate-400">
            <tr>
              <th className="px-6 py-4 font-medium">File</th>
              <th className="px-6 py-4 font-medium">Status</th>
              <th className="px-6 py-4 font-medium">Priority</th>
              <th className="px-6 py-4 font-medium">Confidence</th>
              <th className="px-6 py-4 font-medium">Size</th>
              <th className="px-6 py-4 font-medium"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1E293B]">
            {filtered.map(artifact => (
              <tr key={artifact.id} className="hover:bg-[#1E293B]/30 transition-colors">
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <File className="w-5 h-5 text-slate-500 shrink-0" />
                    <div>
                      <p className="font-medium text-white">{artifact.filename}</p>
                      <p className="text-xs text-slate-400 mt-0.5">
                        {artifact.category}
                      </p>
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4">
                  <StatusBadge status={artifact.status} />
                </td>
                <td className="px-6 py-4">
                  <PriorityBadge priority={artifact.priority} />
                </td>
                <td className="px-6 py-4">
                  <div className="flex items-center gap-3">
                    <span className="font-mono font-medium text-slate-300 w-8">{artifact.confidence_score}%</span>
                    <div className="w-24 h-2 bg-[#0B0F1A] rounded-full overflow-hidden border border-[#1E293B]">
                      <div 
                        className={`h-full rounded-full ${
                          artifact.confidence_score > 80 ? 'bg-sky-400' :
                          artifact.confidence_score > 50 ? 'bg-pink-500' : 'bg-rose-500'
                        }`}
                        style={{ width: `${artifact.confidence_score}%` }}
                      />
                    </div>
                  </div>
                </td>
                <td className="px-6 py-4 text-xs text-slate-300">
                  {artifact.verified_bytes} B verified
                </td>
                <td className="px-6 py-4 text-right">
                  <Link 
                    href={`/artifacts/${artifact.id}`}
                    className="inline-flex items-center gap-1 text-sm font-medium text-sky-400 hover:text-sky-300 transition-colors"
                  >
                    Inspect <ChevronRight className="w-4 h-4" />
                  </Link>
                </td>
              </tr>
            ))}
            
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="px-6 py-8 text-center text-slate-500">
                  {artifacts.length === 0 
                    ? "No artifacts recovered yet. Upload a file to begin analysis."
                    : "No artifacts match the current filters."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
