import EvidenceUpload from "@/components/upload/EvidenceUpload";

export default function Home() {
  return (
    <main className="min-h-screen bg-slate-950 text-slate-200 py-16 px-6">
      <div className="max-w-5xl mx-auto mb-16 text-center">
        <h1 className="text-5xl font-bold tracking-tight text-slate-100 mb-6">
          RECOVER<span className="text-cyan-400">IX</span>
        </h1>
        <p className="text-lg text-slate-400 max-w-3xl mx-auto border-l-2 border-cyan-500 pl-4 text-left italic">
          The deterministic forensic engine establishes what the evidence contains. AI interprets and prioritizes those results. AI never invents missing evidence bytes.
        </p>
      </div>

      <EvidenceUpload />
    </main>
  );
}
