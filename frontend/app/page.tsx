"use client";

import Link from "next/link";
import {
  Shield,
  ArrowRight,
  FileCheck,
  Cpu,
  Layers,
  Search,
  CheckCircle2,
  AlertTriangle,
  FileCode,
  Terminal,
  Lock,
  GitBranch,
} from "lucide-react";

export default function Home() {
  return (
    <div className="min-h-screen bg-[#F8FAFC] text-slate-900 flex flex-col font-sans selection:bg-emerald-500/20 selection:text-emerald-950">
      {/* Hero Section */}
      <section className="relative overflow-hidden pt-20 pb-24 md:pt-28 md:pb-32 border-b border-slate-200/80 bg-gradient-to-b from-white via-[#F8FAFC] to-[#F1F5F9]">
        {/* Subtle decorative grid background */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#E2E8F0_1px,transparent_1px),linear-gradient(to_bottom,#E2E8F0_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)] pointer-events-none opacity-60" />

        <div className="max-w-6xl mx-auto px-6 relative z-10 text-center space-y-8">
          {/* Eyebrow Badge */}
          <div className="inline-flex items-center gap-2.5 px-4 py-1.5 rounded-full bg-white border border-slate-200 shadow-sm text-xs font-mono text-emerald-700">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="font-semibold uppercase tracking-wider">Enterprise Digital Evidence Recovery</span>
            <span className="text-slate-300">|</span>
            <span className="text-slate-600 font-sans">Deterministic V/R/M Standard</span>
          </div>

          {/* Hero Headline */}
          <div className="space-y-5 max-w-4xl mx-auto">
            <h1 className="text-4xl sm:text-6xl md:text-7xl font-bold tracking-tight text-slate-900 font-mono leading-tight">
              Recover What Can Be <span className="text-emerald-600 underline decoration-emerald-500/40 underline-offset-8">Proven</span>.
            </h1>
            <p className="text-lg sm:text-xl text-slate-600 max-w-2xl mx-auto font-sans leading-relaxed">
              Recoverix analyzes damaged digital evidence, reconstructs what can be deterministically established, and clearly separates verified, reconstructed, and missing information.
            </p>
          </div>

          {/* Secondary Message Pillar */}
          <div className="flex flex-wrap items-center justify-center gap-6 sm:gap-10 text-xs font-mono text-slate-600 pt-2">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>No fabricated evidence.</span>
            </div>
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>No hidden assumptions.</span>
            </div>
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>Every recovery result is traceable.</span>
            </div>
          </div>

          {/* Primary Action Buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
            <Link
              href="/setup"
              className="w-full sm:w-auto bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-mono font-bold text-sm px-8 py-4 rounded-xl shadow-md hover:shadow-emerald-500/20 transition-all flex items-center justify-center gap-2"
            >
              <span>EXECUTE RECOVERY</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/cases"
              className="w-full sm:w-auto bg-white hover:bg-slate-50 border border-slate-300 text-slate-700 font-mono text-sm px-6 py-4 rounded-xl shadow-sm transition-colors text-center flex items-center justify-center gap-2"
            >
              <span>View Case History</span>
            </Link>
          </div>

          {/* Hero Visual: Evidence Transformation Pipeline */}
          <div className="pt-12 max-w-4xl mx-auto">
            <div className="bg-white border border-slate-200/90 rounded-2xl p-6 sm:p-8 shadow-xl relative overflow-hidden text-left font-mono">
              <div className="flex items-center justify-between border-b border-slate-200 pb-4 mb-6">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded-full bg-rose-400" />
                  <div className="w-3 h-3 rounded-full bg-amber-400" />
                  <div className="w-3 h-3 rounded-full bg-emerald-400" />
                  <span className="text-xs text-slate-500 ml-2 font-mono">forensic-execution-trace.canvas</span>
                </div>
                <span className="text-[10px] text-emerald-700 font-semibold uppercase tracking-wider bg-emerald-50 px-2.5 py-1 rounded-md border border-emerald-200">
                  REAL EXECUTION TRACE
                </span>
              </div>

              {/* Transformation Visual Diagram */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-center">
                {/* 1. Damaged Evidence */}
                <div className="bg-slate-50 border border-rose-200 p-4 rounded-xl space-y-2">
                  <div className="text-[10px] uppercase font-bold tracking-wider text-rose-600">
                    [1] DAMAGED EVIDENCE
                  </div>
                  <div className="text-xs text-slate-900 font-bold truncate">incident_evidence.bin</div>
                  <div className="text-[11px] text-slate-500">
                    174 Bytes · Unobserved Gap
                  </div>
                  <div className="w-full bg-slate-200 h-3 rounded flex overflow-hidden border border-slate-300 mt-2">
                    <div className="w-2/5 bg-emerald-500" title="Fragment A" />
                    <div className="w-1/5 bg-rose-400" title="Gap" />
                    <div className="w-2/5 bg-emerald-500" title="Fragment B" />
                  </div>
                </div>

                {/* Arrow & Analysis */}
                <div className="bg-slate-50 border border-sky-200 p-4 rounded-xl space-y-2 text-center md:text-left">
                  <div className="text-[10px] uppercase font-bold tracking-wider text-sky-700">
                    [2] DETERMINISTIC ANALYSIS
                  </div>
                  <div className="text-xs text-slate-900 font-bold">Bifragment Reconstruction</div>
                  <div className="text-[11px] text-slate-500">
                    Zero Synthetic Hallucination
                  </div>
                  <div className="text-[11px] text-sky-700 font-semibold mt-2">
                    Verified: 126B · Missing: 48B
                  </div>
                </div>

                {/* 3. Recovered Artifact */}
                <div className="bg-slate-50 border border-emerald-200 p-4 rounded-xl space-y-2">
                  <div className="text-[10px] uppercase font-bold tracking-wider text-emerald-700">
                    [3] RECOVERED ARTIFACT
                  </div>
                  <div className="text-xs text-slate-900 font-bold truncate">recovered_incident_logs.txt</div>
                  <div className="text-[11px] text-slate-500">
                    Validated Structure & Hash
                  </div>
                  <div className="inline-block text-[10px] text-emerald-800 bg-emerald-100 font-semibold px-2 py-0.5 rounded border border-emerald-300 mt-1">
                    STATUS: PARTIALLY RECOVERED
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Product Principles Section */}
      <section id="platform" className="py-20 border-b border-slate-200/80 bg-white">
        <div className="max-w-6xl mx-auto px-6 space-y-12">
          <div className="text-center space-y-3 max-w-2xl mx-auto">
            <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-emerald-600">
              Core Principles
            </h2>
            <h3 className="text-2xl sm:text-3xl font-bold font-mono text-slate-900">
              The Forensic Standard for Data Recovery
            </h3>
            <p className="text-sm text-slate-600">
              Traditional recovery tools either crash on corrupted files or invent plausible data to mask corruption. Recoverix establishes a rigorous scientific alternative.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 font-mono">
            {/* Principle 1: RECOVER */}
            <div className="bg-[#F8FAFC] border border-slate-200 p-6 rounded-2xl space-y-4 hover:border-slate-300 transition-colors shadow-sm">
              <div className="w-10 h-10 rounded-xl bg-emerald-100 border border-emerald-300 flex items-center justify-center text-emerald-700">
                <FileCheck className="w-5 h-5" />
              </div>
              <h4 className="text-lg font-bold text-slate-900 tracking-tight">RECOVER</h4>
              <p className="text-xs text-slate-600 leading-relaxed font-sans">
                Recover usable evidence from damaged or fragmented files. Carves candidates using authoritative signatures and re-assembles bifragment boundaries without risking data corruption.
              </p>
            </div>

            {/* Principle 2: PROVE */}
            <div className="bg-[#F8FAFC] border border-slate-200 p-6 rounded-2xl space-y-4 hover:border-slate-300 transition-colors shadow-sm">
              <div className="w-10 h-10 rounded-xl bg-sky-100 border border-sky-300 flex items-center justify-center text-sky-700">
                <Cpu className="w-5 h-5" />
              </div>
              <h4 className="text-lg font-bold text-slate-900 tracking-tight">PROVE</h4>
              <p className="text-xs text-slate-600 leading-relaxed font-sans">
                Track verified, reconstructed, and missing bytes. Every single byte is audited under our strict V/R/M model, preserving exact offsets and continuous chain of custody.
              </p>
            </div>

            {/* Principle 3: UNDERSTAND */}
            <div className="bg-[#F8FAFC] border border-slate-200 p-6 rounded-2xl space-y-4 hover:border-slate-300 transition-colors shadow-sm">
              <div className="w-10 h-10 rounded-xl bg-amber-100 border border-amber-300 flex items-center justify-center text-amber-700">
                <GitBranch className="w-5 h-5" />
              </div>
              <h4 className="text-lg font-bold text-slate-900 tracking-tight">UNDERSTAND</h4>
              <p className="text-xs text-slate-600 leading-relaxed font-sans">
                Present relationships, confidence, and forensic context. Interactive fragment relationship graphs visualize observed boundaries and unobserved gaps cleanly.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* How It Works Section */}
      <section id="how-it-works" className="py-20 border-b border-slate-200/80 bg-[#F8FAFC]">
        <div className="max-w-6xl mx-auto px-6 space-y-12">
          <div className="text-center space-y-3 max-w-2xl mx-auto">
            <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-sky-700">
              Deterministic Architecture
            </h2>
            <h3 className="text-2xl sm:text-3xl font-bold font-mono text-slate-900">
              Deterministic Byte Accounting Pipeline
            </h3>
            <p className="text-sm text-slate-600">
              Recoverix operates as a stateful, reproducible pipeline without non-deterministic AI hallucinations during byte recovery.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center font-mono">
            <div className="space-y-4 text-xs">
              <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm space-y-1.5">
                <span className="text-emerald-700 font-bold uppercase">[1] Ingestion & Signature Scanning</span>
                <p className="text-slate-600 font-sans text-xs">
                  Evidence buffers are analyzed in memory. Candidate headers and trailers are located using authoritative magic bytes and marker sequences.
                </p>
              </div>

              <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm space-y-1.5">
                <span className="text-sky-700 font-bold uppercase">[2] Bounded Bifragment Assembly</span>
                <p className="text-slate-600 font-sans text-xs">
                  Separated header and trailer fragments are bounded and verified. Missing middle bytes are isolated as verified gaps rather than synthetic filler.
                </p>
              </div>

              <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm space-y-1.5">
                <span className="text-amber-700 font-bold uppercase">[3] Structural Validation & Bounds Check</span>
                <p className="text-slate-600 font-sans text-xs">
                  Format-specific parsers validate delimiters, row lengths, cross-reference tables, and syntax constraints defensively.
                </p>
              </div>

              <div className="p-4 rounded-xl bg-white border border-slate-200 shadow-sm space-y-1.5">
                <span className="text-emerald-700 font-bold uppercase">[4] 100-Point Confidence Scoring</span>
                <p className="text-slate-600 font-sans text-xs">
                  An objective rubric scores Header (20), Footer (20), Structure (30), Size (15), and Integrity (15) for court-ready reports.
                </p>
              </div>
            </div>

            <div className="bg-white border border-slate-200 rounded-2xl p-6 text-xs text-slate-800 space-y-4 shadow-sm">
              <div className="flex items-center justify-between border-b border-slate-200 pb-3">
                <span className="text-slate-900 font-bold">FORENSIC INTEGRITY GUARANTEE</span>
                <Lock className="w-4 h-4 text-emerald-600" />
              </div>
              <p className="font-sans leading-relaxed text-slate-600">
                In court and incident response, an invented byte invalidates evidence. Recoverix guarantees that:
              </p>
              <ul className="space-y-2 text-[11px] font-sans">
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                  <span>Missing regions are explicitly counted and tagged as <code className="font-mono bg-rose-50 text-rose-700 px-1 py-0.5 rounded border border-rose-200">MISSING</code>.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                  <span>Synthetically repaired container structures are tagged as <code className="font-mono bg-sky-50 text-sky-700 px-1 py-0.5 rounded border border-sky-200">RECONSTRUCTED</code>.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                  <span>Unmodified evidence is tagged as <code className="font-mono bg-emerald-50 text-emerald-700 px-1 py-0.5 rounded border border-emerald-200">VERIFIED</code>.</span>
                </li>
              </ul>
              <div className="pt-2">
                <Link
                  href="/setup"
                  className="w-full bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold py-3 rounded-xl text-center block transition-colors shadow-sm"
                >
                  START RECOVERY INVESTIGATION →
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Supported Evidence Section */}
      <section id="evidence" className="py-20 border-b border-slate-200/80 bg-white">
        <div className="max-w-6xl mx-auto px-6 space-y-12">
          <div className="text-center space-y-3 max-w-2xl mx-auto">
            <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-500">
              Evidence Capabilities
            </h2>
            <h3 className="text-2xl sm:text-3xl font-bold font-mono text-slate-900">
              Supported Evidence Formats & Capabilities
            </h3>
            <p className="text-sm text-slate-600">
              Recoverix distinguishes between full structural reconstruction and defensive signature carving across 7 formats.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 font-mono text-xs">
            {/* Category A: Recovery & Reconstruction */}
            <div className="bg-[#F8FAFC] border border-emerald-200 p-6 rounded-2xl space-y-4 shadow-sm">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-bold text-emerald-800 uppercase tracking-wider">
                  Full Recovery & Reconstruction
                </h4>
                <span className="text-[10px] bg-emerald-100 text-emerald-800 font-semibold border border-emerald-200 px-2 py-0.5 rounded">
                  TIER 1 SUPPORT
                </span>
              </div>
              <p className="text-slate-600 font-sans">
                Full deterministic carving, structural validation, UTF-8 normalization, and bounded bifragment gap assembly.
              </p>
              <div className="grid grid-cols-2 gap-3 pt-2">
                <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-xs">
                  <div className="text-slate-900 font-bold">TXT</div>
                  <div className="text-[11px] text-slate-500 font-sans mt-0.5">UTF-8 bounds, gap isolation, text structure</div>
                </div>
                <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-xs">
                  <div className="text-slate-900 font-bold">CSV</div>
                  <div className="text-[11px] text-slate-500 font-sans mt-0.5">Delimiter detection, column alignment, RFC-4180</div>
                </div>
                <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-xs">
                  <div className="text-slate-900 font-bold">JSON</div>
                  <div className="text-[11px] text-slate-500 font-sans mt-0.5">Token balancing, syntax repair, tree validation</div>
                </div>
                <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-xs">
                  <div className="text-slate-900 font-bold">PDF</div>
                  <div className="text-[11px] text-slate-500 font-sans mt-0.5">Trailer salvage, cross-reference (xref) rebuild, un-shuffling</div>
                </div>
              </div>
            </div>

            {/* Category B: Detection & Validation */}
            <div className="bg-[#F8FAFC] border border-sky-200 p-6 rounded-2xl space-y-4 shadow-sm">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-bold text-sky-800 uppercase tracking-wider">
                  Detection & Validation
                </h4>
                <span className="text-[10px] bg-sky-100 text-sky-800 font-semibold border border-sky-200 px-2 py-0.5 rounded">
                  TIER 2 SUPPORT
                </span>
              </div>
              <p className="text-slate-600 font-sans">
                Authoritative magic signature detection, chunk parsing, CRC validation, and structural container bounding.
              </p>
              <div className="grid grid-cols-3 gap-3 pt-2">
                <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-xs">
                  <div className="text-slate-900 font-bold">PNG</div>
                  <div className="text-[11px] text-slate-500 font-sans mt-0.5">IHDR, IDAT, IEND chunk validation</div>
                </div>
                <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-xs">
                  <div className="text-slate-900 font-bold">JPEG</div>
                  <div className="text-[11px] text-slate-500 font-sans mt-0.5">SOI, APP0, SOF0, EOI marker pairing</div>
                </div>
                <div className="p-3 bg-white rounded-lg border border-slate-200 shadow-xs">
                  <div className="text-slate-900 font-bold">XML</div>
                  <div className="text-[11px] text-slate-500 font-sans mt-0.5">Well-formedness check, root tag balancing</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer id="about" className="py-12 bg-white text-xs font-mono text-slate-500 border-t border-slate-200">
        <div className="max-w-6xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-emerald-600" />
            <span className="text-slate-900 font-bold">RECOVERIX</span>
            <span>— Deterministic Digital Evidence Recovery</span>
          </div>
          <div className="text-center sm:text-right text-slate-600 font-sans">
            Every recovery result is traceable. Zero synthetic hallucination.
          </div>
        </div>
      </footer>
    </div>
  );
}
