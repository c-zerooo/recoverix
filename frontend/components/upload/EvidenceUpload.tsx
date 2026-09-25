"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { UploadCloud, File, Database, Image as ImageIcon, FileText, Loader2, CheckCircle } from "lucide-react";

const LOADING_STEPS = [
  "Reading image & computing SHA-256 hash...",
  "Scanning chunks & controlled format signatures...",
  "Contiguous carving & bounded bifragment reconstruction (MAX_GAP=4096)...",
  "Running structural validation & 0-100 confidence scoring..."
];

export default function EvidenceUpload() {
  const router = useRouter();
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);

  const startAnalysis = () => {
    setIsAnalyzing(true);
    setCurrentStep(0);
  };

  useEffect(() => {
    if (isAnalyzing) {
      if (currentStep < LOADING_STEPS.length) {
        const timer = setTimeout(() => {
          setCurrentStep(prev => prev + 1);
        }, 400); // 400ms per step * 4 steps = 1.6s
        return () => clearTimeout(timer);
      } else {
        router.push('/dashboard');
      }
    }
  }, [isAnalyzing, currentStep, router]);

  return (
    <div className="w-full max-w-5xl mx-auto space-y-8">
      {/* Upload Area */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 flex flex-col items-center justify-center text-center">
        <div className="w-16 h-16 bg-slate-800 rounded-full flex items-center justify-center mb-6">
          <UploadCloud className="w-8 h-8 text-cyan-400" />
        </div>
        <h2 className="text-2xl font-semibold text-slate-100 mb-2">Upload Forensic Image</h2>
        <p className="text-slate-400 max-w-md mb-8">
          Select .img, .raw, .dd, or .bin files to begin deterministic analysis.
        </p>
        
        <div className="flex gap-4 mb-8 text-sm text-slate-500">
          <div className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-emerald-400" /> Maximum evidence image: 5 MB
          </div>
          <div className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-emerald-400" /> Max bifragment gap: 4096 bytes
          </div>
          <div className="flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-emerald-400" /> Synchronous analysis
          </div>
        </div>

        <button 
          onClick={startAnalysis}
          disabled={isAnalyzing}
          className="bg-cyan-500 hover:bg-cyan-600 text-slate-950 font-semibold py-3 px-8 rounded-lg transition-colors disabled:opacity-50"
        >
          Select File & Analyze
        </button>
      </div>

      {/* Sample Cases */}
      <div>
        <h3 className="text-xl font-semibold text-slate-200 mb-4">Or Load a Sample Case</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <button onClick={startAnalysis} disabled={isAnalyzing} className="text-left bg-slate-900 border border-slate-800 p-6 rounded-xl hover:border-cyan-500/50 transition-colors group">
            <Database className="w-6 h-6 text-cyan-400 mb-4 group-hover:scale-110 transition-transform" />
            <h4 className="font-semibold text-slate-200 mb-1">Fragmented CSV</h4>
            <p className="text-sm text-slate-400">Bounded bifragment gap reconstruction</p>
          </button>
          
          <button onClick={startAnalysis} disabled={isAnalyzing} className="text-left bg-slate-900 border border-slate-800 p-6 rounded-xl hover:border-emerald-500/50 transition-colors group">
            <ImageIcon className="w-6 h-6 text-emerald-400 mb-4 group-hover:scale-110 transition-transform" />
            <h4 className="font-semibold text-slate-200 mb-1">Corrupted PNG</h4>
            <p className="text-sm text-slate-400">Defensive chunk bounds check</p>
          </button>

          <button onClick={startAnalysis} disabled={isAnalyzing} className="text-left bg-slate-900 border border-slate-800 p-6 rounded-xl hover:border-cyan-500/50 transition-colors group">
            <FileText className="w-6 h-6 text-cyan-400 mb-4 group-hover:scale-110 transition-transform" />
            <h4 className="font-semibold text-slate-200 mb-1">Damaged TXT</h4>
            <p className="text-sm text-slate-400">Contiguous carving with synthetic markers</p>
          </button>
        </div>
      </div>

      {/* Loading Overlay */}
      {isAnalyzing && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-8 max-w-lg w-full">
            <div className="flex items-center justify-center mb-8">
              <Loader2 className="w-12 h-12 text-cyan-400 animate-spin" />
            </div>
            <h3 className="text-xl font-semibold text-slate-200 mb-6 text-center">Analyzing Evidence</h3>
            <div className="space-y-4">
              {LOADING_STEPS.map((step, idx) => (
                <div key={idx} className={`flex items-center gap-3 text-sm ${idx <= currentStep ? 'text-slate-300' : 'text-slate-600'}`}>
                  {idx < currentStep ? (
                    <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0" />
                  ) : idx === currentStep ? (
                    <Loader2 className="w-5 h-5 text-cyan-400 animate-spin shrink-0" />
                  ) : (
                    <div className="w-5 h-5 rounded-full border border-slate-700 shrink-0" />
                  )}
                  <span>{step}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
