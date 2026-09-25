"use client";

import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { UploadCloud, Loader2, CheckCircle } from "lucide-react";
import { createCase, uploadEvidence, analyzeCase } from "../../lib/api";

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
  const fileInputRef = useRef<HTMLInputElement>(null);

  const executePipeline = async (file: File, caseName: string) => {
    setIsAnalyzing(true);
    setCurrentStep(0);

    const interval = setInterval(() => {
      setCurrentStep(prev => (prev < LOADING_STEPS.length ? prev + 1 : prev));
    }, 400);

    try {
      const newCase = await createCase(caseName);
      await uploadEvidence(newCase.id, file);
      await analyzeCase(newCase.id);
      
      clearInterval(interval);
      setCurrentStep(LOADING_STEPS.length);
      
      localStorage.setItem('recoverix_active_case_id', newCase.id);
      setTimeout(() => {
        router.push(`/dashboard?case_id=${newCase.id}`);
      }, 400);
    } catch (e) {
      console.error(e);
      clearInterval(interval);
      router.push(`/dashboard`);
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      executePipeline(file, `Uploaded Case: ${file.name}`);
    }
  };

  return (
    <div className="w-full max-w-xl mx-auto mt-20 bg-[#111622] border border-white/[0.08] rounded-2xl p-10 shadow-2xl text-center">
      <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-pink-500/20 to-sky-500/20 border border-pink-500/30 flex items-center justify-center mx-auto mb-5">
        <UploadCloud className="w-6 h-6 text-pink-500" />
      </div>
      <h2 className="text-xl font-semibold tracking-tight text-white">Upload Disk Image</h2>
      <p className="text-sm text-slate-400 mt-1.5 mb-7">
        Select a .img, .raw, .dd, or .bin file up to 5 MB to recover artifacts.
      </p>

      <input 
        type="file" 
        ref={fileInputRef} 
        onChange={handleFileUpload} 
        className="hidden" 
        accept=".img,.raw,.dd,.bin"
      />
      
      <button 
        onClick={() => fileInputRef.current?.click()}
        disabled={isAnalyzing}
        className="bg-gradient-to-r from-pink-500 to-rose-500 hover:from-pink-600 hover:to-rose-600 text-white text-sm font-medium px-6 py-2.5 rounded-lg shadow-sm transition-all inline-flex items-center gap-2 disabled:opacity-50"
      >
        {isAnalyzing ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" /> Analyzing...
          </>
        ) : (
          'Select File & Analyze'
        )}
      </button>

      {/* Loading Overlay */}
      {isAnalyzing && (
        <div className="fixed inset-0 bg-[#0B0F1A]/80 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-[#111622] border border-white/[0.08] rounded-2xl p-8 max-w-lg w-full">
            <div className="flex items-center justify-center mb-8">
              <Loader2 className="w-12 h-12 text-pink-500 animate-spin" />
            </div>
            <h3 className="text-xl font-semibold tracking-tight text-white mb-6 text-center">Analyzing Evidence</h3>
            <div className="space-y-4">
              {LOADING_STEPS.map((step, idx) => (
                <div key={idx} className={`flex items-center gap-3 text-sm ${idx <= currentStep ? 'text-slate-300' : 'text-slate-600'}`}>
                  {idx < currentStep ? (
                    <CheckCircle className="w-5 h-5 text-pink-500 shrink-0" />
                  ) : idx === currentStep ? (
                    <Loader2 className="w-5 h-5 text-sky-400 animate-spin shrink-0" />
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
