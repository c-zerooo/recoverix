import { Artifact, Case, AIExplanation } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK !== 'false';

export const mockArtifacts: Artifact[] = [
  {
    id: "artifact_001",
    filename: "ledger.csv",
    mime_type: "text/csv",
    category: "DATABASE_LOG",
    priority: "HIGH",
    confidence_score: 78,
    confidence_breakdown: {
      header_validity: 20,
      footer_validity: 0,
      structural_validation: 28,
      size_plausibility: 15,
      reconstruction_integrity: 15,
      total: 78
    },
    status: "PARTIALLY_RECOVERED",
    verified_bytes: 8400,
    reconstructed_bytes: 1200,
    missing_bytes: 400,
    reconstruction_method: "BIFRAGMENT_GAP",
    validation: {
      valid: true,
      checks: [
        { name: "Header Signature", detail: "Valid CSV header found.", passed: true },
        { name: "Row Integrity", detail: "Some rows span gap boundaries, partially recovered.", passed: true }
      ]
    },
    fragments: [
      { id: "frag_1", start_offset: 0, end_offset: 8400, type: "VERIFIED" },
      { id: "frag_2", start_offset: 8400, end_offset: 9600, type: "RECONSTRUCTED_GAP" }
    ],
    preview_text: "id,amount,date,status\n1,500.00,2026-09-21,COMPLETED\n2,250.00,2026-09-22,PENDING\n...",
    ai_summary: {
      summary: "Financial ledger with missing trailing records.",
      details: [
        "Recovered: Core transaction history (8400 bytes).",
        "Verified: CSV headers and contiguous block.",
        "Missing: Expected footer/EOF marker (400 bytes missing).",
        "Status reasoning: Received score 78 due to bifragment gap reconstruction.",
        "Priority reasoning: HIGH due to financial nature of the logs."
      ]
    }
  },
  {
    id: "artifact_002",
    filename: "auth_trace.txt",
    mime_type: "text/plain",
    category: "SYSTEM_TRACE",
    priority: "CRITICAL",
    confidence_score: 92,
    confidence_breakdown: {
      header_validity: 20,
      footer_validity: 20,
      structural_validation: 22,
      size_plausibility: 15,
      reconstruction_integrity: 15,
      total: 92
    },
    status: "FULLY_RECOVERED",
    verified_bytes: 1500,
    reconstructed_bytes: 0,
    missing_bytes: 0,
    reconstruction_method: "CONTIGUOUS",
    validation: {
      valid: true,
      checks: [
        { name: "Contiguous Block", detail: "All bytes in single valid block.", passed: true }
      ]
    },
    fragments: [
      { id: "frag_1", start_offset: 0, end_offset: 1500, type: "VERIFIED" }
    ],
    preview_text: "2026-09-21T08:15:02Z AUTH_SUCCESS user=admin\n2026-09-21T08:15:05Z SUDO_EXEC cmd=/bin/sh\n...",
    ai_summary: {
      summary: "Critical authentication logs fully recovered.",
      details: [
        "Recovered: Complete authentication trace.",
        "Verified: Entire 1500 byte file is contiguous and intact.",
        "Missing: None.",
        "Status reasoning: 92/100 score as fully recovered, contiguous block.",
        "Priority reasoning: CRITICAL due to evidence of privileged execution."
      ]
    }
  },
  {
    id: "artifact_003",
    filename: "evidence_capture.png",
    mime_type: "image/png",
    category: "PHOTO_MEDIA",
    priority: "HIGH",
    confidence_score: 34,
    confidence_breakdown: {
      header_validity: 20,
      footer_validity: 0,
      structural_validation: 14,
      size_plausibility: 0,
      reconstruction_integrity: 0,
      total: 34
    },
    status: "CORRUPTED",
    verified_bytes: 2000,
    reconstructed_bytes: 1000,
    missing_bytes: 500,
    reconstruction_method: "NONE",
    validation: {
      valid: false,
      error: "declared chunk exceeds remaining evidence",
      checks: [
        { name: "PNG Header", detail: "Valid PNG magic bytes.", passed: true },
        { name: "IHDR Chunk", detail: "Image header parsed.", passed: true },
        { name: "IDAT Chunk bounds", detail: "Declared chunk exceeds remaining evidence.", passed: false }
      ]
    },
    fragments: [
      { id: "frag_1", start_offset: 0, end_offset: 2000, type: "VERIFIED" },
      { id: "frag_2", start_offset: 2000, end_offset: 2500, type: "MISSING" }
    ],
    preview_text: "<PNG binary data unrenderable>",
    ai_summary: {
      summary: "Corrupted image file with truncated payload.",
      details: [
        "Recovered: Partial image headers.",
        "Verified: Valid PNG magic bytes.",
        "Missing: Image payload and footer.",
        "Status reasoning: CORRUPTED due to invalid IDAT bounds check.",
        "Priority reasoning: HIGH as potential photo evidence."
      ]
    }
  },
  {
    id: "artifact_004",
    filename: "damaged_sector.txt",
    mime_type: "text/plain",
    category: "DOCUMENT",
    priority: "LOW",
    confidence_score: 12,
    confidence_breakdown: {
      header_validity: 0,
      footer_validity: 0,
      structural_validation: 12,
      size_plausibility: 0,
      reconstruction_integrity: 0,
      total: 12
    },
    status: "UNRECOVERABLE",
    verified_bytes: 100,
    reconstructed_bytes: 0,
    missing_bytes: 900,
    reconstruction_method: "NONE",
    validation: {
      valid: false,
      error: "no valid header found",
      checks: [
        { name: "Magic Bytes", detail: "No valid header found.", passed: false }
      ]
    },
    fragments: [
      { id: "frag_1", start_offset: 0, end_offset: 100, type: "VERIFIED" }
    ],
    preview_text: "\\x00\\x00\\x00... (unintelligible sector noise)",
    ai_summary: {
      summary: "Completely unrecoverable damaged sector.",
      details: [
        "Recovered: None.",
        "Verified: 100 bytes of raw data, completely unrecognizable.",
        "Missing: Essentially all content (900 expected bytes).",
        "Status reasoning: UNRECOVERABLE due to lack of headers and structure.",
        "Priority reasoning: LOW because no intelligible data exists."
      ]
    }
  }
];

export const mockCase: Case = {
  id: "case_001",
  name: "Operation Phantom",
  description: "Investigation into unauthorized access.",
  artifacts: mockArtifacts
};

export async function analyzeEvidence(payload?: { filename?: string; sampleId?: string }): Promise<Case> {
  if (!USE_MOCK) {
    try {
      const res = await fetch(`${API_BASE}/api/cases/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
        cache: 'no-store'
      });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn("Backend unreachable, falling back to mock", e);
    }
  }
  return mockCase;
}

export async function fetchCase(caseId = 'case_001'): Promise<Case> {
  if (!USE_MOCK) {
    try {
      const res = await fetch(`${API_BASE}/api/cases/${caseId}`, { cache: 'no-store' });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn("Backend unreachable, falling back to mock", e);
    }
  }
  return mockCase;
}

export async function fetchArtifacts(caseId = 'case_001'): Promise<Artifact[]> {
  if (!USE_MOCK) {
    try {
      const res = await fetch(`${API_BASE}/api/cases/${caseId}/artifacts`, { cache: 'no-store' });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn("Backend unreachable, falling back to mock", e);
    }
  }
  return mockArtifacts;
}

export async function fetchArtifactById(artifactId: string): Promise<Artifact> {
  if (!USE_MOCK) {
    try {
      const res = await fetch(`${API_BASE}/api/artifacts/${artifactId}`, { cache: 'no-store' });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn("Backend unreachable, falling back to mock", e);
    }
  }
  const artifact = mockArtifacts.find(a => a.id === artifactId);
  if (!artifact) throw new Error("Artifact not found");
  return artifact;
}

export async function fetchArtifactExplanation(artifactId: string): Promise<AIExplanation> {
  if (!USE_MOCK) {
    try {
      const res = await fetch(`${API_BASE}/api/artifacts/${artifactId}/explain`, {
        method: 'POST',
        cache: 'no-store'
      });
      if (res.ok) return await res.json();
    } catch (e) {
      console.warn("Backend unreachable, falling back to mock", e);
    }
  }
  const artifact = mockArtifacts.find(a => a.id === artifactId);
  if (!artifact || !artifact.ai_summary) throw new Error("Explanation not available");
  return artifact.ai_summary;
}
