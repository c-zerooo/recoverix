"use client";

import { useState } from "react";
import {
  ForensicFragment,
  DamageRegion,
  ReconstructionStep,
} from "@/lib/types";
import {
  FileText,
  ShieldCheck,
  AlertTriangle,
  Cpu,
  Info,
} from "lucide-react";

interface FragmentGraphProps {
  filename: string;
  totalBytes: number;
  fragments: ForensicFragment[];
  damageRegions: DamageRegion[];
  reconstructionSteps: ReconstructionStep[];
}

export function FragmentGraph({
  filename,
  totalBytes,
  fragments,
  damageRegions,
  reconstructionSteps,
}: FragmentGraphProps) {
  // Currently selected/hovered node for detail inspector
  const [selectedNode, setSelectedNode] = useState<{
    id: string;
    type: "ROOT" | "FRAGMENT" | "GAP" | "RECONSTRUCTION" | "CONTIGUOUS";
    label: string;
    offsetRange: string;
    length: string;
    status: string;
    source: string;
    description: string;
  }>({
    id: "root",
    type: "ROOT",
    label: filename,
    offsetRange: `0 B – ${totalBytes} B`,
    length: `${totalBytes} Bytes`,
    status: "ORIGINAL EVIDENCE SOURCE",
    source: "Uploaded Evidence File",
    description: "Target evidence container analyzed by deterministic carving and validation.",
  });

  const isFragmented = fragments.length > 1;
  const isContiguous = fragments.length === 1 && damageRegions.length === 0;
  const isShuffled = reconstructionSteps.some((s) => s.method === "FRAGMENT_UNSHUFFLE");

  return (
    <div className="bg-white border border-slate-200/90 rounded-2xl p-6 sm:p-8 space-y-6 shadow-xs font-mono">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500" />
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-900">
              Fragment Relationship Graph
            </h3>
          </div>
          <p className="text-xs text-slate-600 font-sans mt-0.5">
            Real hierarchical structure derived directly from observed candidate offsets and gaps.
          </p>
        </div>

        <div className="flex items-center gap-2 text-[11px]">
          <span className="bg-slate-100 text-slate-700 border border-slate-200 px-2.5 py-1 rounded font-medium">
            NODES: {isContiguous ? 2 : fragments.length + damageRegions.length + 1}
          </span>
          <span className="bg-emerald-50 text-emerald-800 border border-emerald-200 px-2.5 py-1 rounded font-semibold">
            ZERO HALLUCINATION
          </span>
        </div>
      </div>

      {/* Visual Canvas Area */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Interactive Graph Tree (Cols 1-8) */}
        <div className="lg:col-span-8 bg-slate-50/80 border border-slate-200 rounded-xl p-6 relative overflow-x-auto min-h-[360px] flex flex-col items-center justify-center">
          {/* ROOT NODE: ORIGINAL EVIDENCE */}
          <div
            onClick={() =>
              setSelectedNode({
                id: "root",
                type: "ROOT",
                label: filename,
                offsetRange: `0 B – ${totalBytes} B`,
                length: `${totalBytes} Bytes`,
                status: "ORIGINAL EVIDENCE SOURCE",
                source: "Input Stream",
                description: "Full unparsed evidence container submitted for forensic examination.",
              })
            }
            className={`cursor-pointer px-5 py-3 rounded-xl border text-center transition-all shadow-2xs ${
              selectedNode.id === "root"
                ? "bg-slate-900 text-white border-slate-900 shadow-md scale-105"
                : "bg-white border-slate-300 text-slate-800 hover:border-slate-400"
            }`}
          >
            <div className={`text-[10px] uppercase tracking-wider font-semibold ${
              selectedNode.id === "root" ? "text-slate-300" : "text-slate-500"
            }`}>
              ORIGINAL EVIDENCE
            </div>
            <div className="text-sm font-bold flex items-center justify-center gap-1.5 mt-0.5">
              <FileText className={`w-4 h-4 ${selectedNode.id === "root" ? "text-emerald-400" : "text-emerald-600"}`} />
              <span>{filename}</span>
            </div>
            <div className={`text-[10px] mt-1 ${
              selectedNode.id === "root" ? "text-slate-300" : "text-slate-500"
            }`}>
              {totalBytes} Bytes
            </div>
          </div>

          {/* SVG Connector Lines */}
          <div className="w-full flex justify-center py-2">
            <div className="w-0.5 h-6 bg-slate-300" />
          </div>

          {/* CASE A: FRAGMENTED EVIDENCE WITH REAL GAPS */}
          {isFragmented ? (
            <div className="w-full space-y-4">
              {/* Branching Bar */}
              <div className="relative w-3/4 mx-auto border-t-2 border-slate-300 pt-4">
                <div className="absolute top-0 left-0 w-0.5 h-4 bg-slate-300" />
                <div className="absolute top-0 right-0 w-0.5 h-4 bg-slate-300" />
              </div>

              {/* Fragment Nodes (A and B) */}
              <div className="grid grid-cols-2 gap-4 max-w-xl mx-auto">
                {fragments.map((frag, idx) => {
                  const fragLabel = idx === 0 ? "FRAGMENT A" : idx === 1 ? "FRAGMENT B" : `FRAGMENT ${idx + 1}`;
                  const isSelected = selectedNode.id === frag.fragment_id;

                  return (
                    <div
                      key={frag.fragment_id}
                      onClick={() =>
                        setSelectedNode({
                          id: frag.fragment_id,
                          type: "FRAGMENT",
                          label: `${fragLabel} [${frag.fragment_id}]`,
                          offsetRange: `${frag.offset} B – ${frag.end_offset} B`,
                          length: `${frag.length} Bytes`,
                          status: frag.status,
                          source: frag.source || "text_structure",
                          description:
                            "Contiguous verified segment located by format boundary and structure parser. Zero mutated bytes.",
                        })
                      }
                      className={`cursor-pointer p-4 rounded-xl border text-left transition-all ${
                        isSelected
                          ? "bg-emerald-50 border-2 border-emerald-600 text-emerald-950 shadow-md shadow-emerald-500/10 scale-105"
                          : "bg-white border border-emerald-300 hover:border-emerald-500 text-slate-800 shadow-2xs"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-[10px] uppercase font-bold text-emerald-700">
                          {fragLabel}
                        </span>
                        <span className="text-[9px] bg-emerald-100 text-emerald-800 font-semibold px-1.5 py-0.5 rounded">
                          {frag.status}
                        </span>
                      </div>
                      <div className="text-xs font-bold text-slate-900">
                        {frag.offset} B – {frag.end_offset} B
                      </div>
                      <div className="text-[11px] text-slate-500 mt-1">
                        Length: {frag.length} B
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Central Relationship Connection */}
              {isShuffled ? (
                <div className="flex flex-col items-center pt-2">
                  <div className="w-0.5 h-6 bg-slate-300" />
                  <div
                    onClick={() =>
                      setSelectedNode({
                        id: "shuffled-rel",
                        type: "RECONSTRUCTION",
                        label: "SHUFFLED SEQUENCE REORDERED",
                        offsetRange: `Unshuffle Offset: ${fragments[0]?.offset ?? 0} B`,
                        length: `${totalBytes} Bytes`,
                        status: "RECONSTRUCTED (REORDERED)",
                        source: "Deterministic Sequence Alignment",
                        description:
                          "PDF header fragment and trailer fragment were detected in reverse order in raw evidence. Deterministic un-shuffling reordered the fragments into valid document sequence without inventing data.",
                      })
                    }
                    className={`cursor-pointer max-w-sm w-full p-3 rounded-xl border text-center transition-all ${
                      selectedNode.id === "shuffled-rel"
                        ? "bg-sky-50 border-2 border-sky-600 text-sky-950 shadow-md shadow-sky-500/10 scale-105"
                        : "bg-white border border-sky-300 hover:border-sky-500 text-slate-800 shadow-2xs"
                    }`}
                  >
                    <div className="flex items-center justify-center gap-1.5 text-sky-700 text-xs font-bold uppercase">
                      <Cpu className="w-3.5 h-3.5" />
                      <span>SHUFFLED SEQUENCE (REORDERED)</span>
                    </div>
                    <div className="text-[11px] text-slate-600 mt-0.5">
                      Offset: {fragments[0]?.offset ?? 0} B · Zero Missing Bytes
                    </div>
                  </div>
                </div>
              ) : damageRegions.length > 0 ? (
                <div className="flex flex-col items-center pt-2">
                  <div className="w-0.5 h-6 bg-slate-300" />
                  {damageRegions.map((dmg) => {
                    const isSelected = selectedNode.id === dmg.region_id;
                    return (
                      <div
                        key={dmg.region_id}
                        onClick={() =>
                          setSelectedNode({
                            id: dmg.region_id,
                            type: "GAP",
                            label: `OBSERVED BYTE GAP [${dmg.region_id}]`,
                            offsetRange: `${dmg.start_offset} B – ${dmg.end_offset} B`,
                            length: `${dmg.length} Bytes`,
                            status: "MISSING (UNRECOVERABLE)",
                            source: "Evidence Discontinuity",
                            description:
                              "Missing byte span cannot be deterministically inferred. Recoverix preserves this gap as unobserved evidence.",
                          })
                        }
                        className={`cursor-pointer max-w-sm w-full p-3 rounded-xl border text-center transition-all ${
                          isSelected
                            ? "bg-amber-50 border-2 border-amber-600 text-amber-950 shadow-md shadow-amber-500/10 scale-105"
                            : "bg-amber-50/60 border border-amber-300 hover:border-amber-500 text-slate-800 shadow-2xs"
                        }`}
                      >
                        <div className="flex items-center justify-center gap-1.5 text-amber-700 text-xs font-bold uppercase">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          <span>OBSERVED BYTE GAP: {dmg.length} B</span>
                        </div>
                        <div className="text-[11px] text-slate-600 mt-0.5">
                          Gap Offsets: {dmg.start_offset} B – {dmg.end_offset} B
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : null}
            </div>
          ) : isContiguous ? (
            /* CASE B: CONTIGUOUS UNFRAGMENTED EVIDENCE */
            <div className="w-full flex flex-col items-center space-y-2">
              <div
                onClick={() =>
                  setSelectedNode({
                    id: "contiguous",
                    type: "CONTIGUOUS",
                    label: "CONTIGUOUS VERIFIED EVIDENCE",
                    offsetRange: `0 B – ${totalBytes} B`,
                    length: `${totalBytes} Bytes`,
                    status: "VERIFIED INTACT",
                    source: "Direct Header-to-EOF Parsing",
                    description: "Continuous valid stream with zero fragmented boundaries or missing regions.",
                  })
                }
                className={`cursor-pointer max-w-md w-full p-4 rounded-xl border text-center transition-all ${
                  selectedNode.id === "contiguous"
                    ? "bg-emerald-50 border-2 border-emerald-600 text-emerald-950 scale-105 shadow-md shadow-emerald-500/10"
                    : "bg-white border border-emerald-300 hover:border-emerald-500 text-slate-800 shadow-2xs"
                }`}
              >
                <div className="flex items-center justify-center gap-1.5 text-emerald-700 text-xs font-bold uppercase mb-1">
                  <ShieldCheck className="w-4 h-4" />
                  <span>CONTIGUOUS EVIDENCE (0 → {totalBytes} B)</span>
                </div>
                <div className="text-[11px] text-slate-600">
                  Status: VERIFIED INTACT · 0 Missing Gaps
                </div>
              </div>
            </div>
          ) : (
            /* Generic/Carved fallback */
            <div className="text-xs text-slate-500 italic py-4">
              Single carved candidate validated.
            </div>
          )}
        </div>

        {/* Node Detail Inspector (Cols 9-12) */}
        <div className="lg:col-span-4 bg-slate-50 border border-slate-200 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-200 pb-3">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
              <Info className="w-3.5 h-3.5 text-emerald-600" />
              <span>Node Inspector</span>
            </span>
            <span className="text-[10px] text-slate-500 font-medium">CLICK TO SELECT</span>
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <span className="text-slate-500 text-[10px] uppercase font-semibold block">Selected Element</span>
              <span className="text-slate-900 font-bold block truncate">{selectedNode.label}</span>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="bg-white p-2.5 rounded-lg border border-slate-200 shadow-2xs">
                <span className="text-slate-500 text-[9px] uppercase font-semibold block">Offset Range</span>
                <span className="text-slate-800 font-semibold">{selectedNode.offsetRange}</span>
              </div>
              <div className="bg-white p-2.5 rounded-lg border border-slate-200 shadow-2xs">
                <span className="text-slate-500 text-[9px] uppercase font-semibold block">Byte Length</span>
                <span className="text-emerald-700 font-semibold">{selectedNode.length}</span>
              </div>
            </div>

            <div>
              <span className="text-slate-500 text-[10px] uppercase font-semibold block">Forensic Status</span>
              <span
                className={`inline-block px-2.5 py-0.5 rounded text-[11px] font-bold mt-0.5 border ${
                  selectedNode.status.includes("VERIFIED")
                    ? "bg-emerald-100 text-emerald-800 border-emerald-300"
                    : selectedNode.status.includes("MISSING")
                    ? "bg-amber-100 text-amber-800 border-amber-300"
                    : "bg-slate-200 text-slate-800 border-slate-300"
                }`}
              >
                {selectedNode.status}
              </span>
            </div>

            <div>
              <span className="text-slate-500 text-[10px] uppercase font-semibold block">Evidence Origin</span>
              <span className="text-slate-700 text-[11px]">{selectedNode.source}</span>
            </div>

            <div className="pt-2 border-t border-slate-200">
              <span className="text-slate-500 text-[10px] uppercase font-semibold block mb-1">Evidentiary Value</span>
              <p className="text-[11px] text-slate-600 font-sans leading-relaxed">
                {selectedNode.description}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
