import { Artifact, Case } from './types';

export const mockArtifacts: Artifact[] = [
  {
    id: "artifact_001",
    filename: "ledger.csv",
    mime_type: "text/csv",
    category: "DATABASE_LOG",
    priority: "HIGH",
    confidence_score: 78,
    status: "PARTIALLY_RECOVERED",
    verified_bytes: 8400,
    reconstructed_bytes: 1200,
    missing_bytes: 400,
    reconstruction_method: "BIFRAGMENT_GAP",
    validation: { valid: true },
    fragments: [],
    ai_summary: null
  },
  {
    id: "artifact_002",
    filename: "auth_trace.txt",
    mime_type: "text/plain",
    category: "SYSTEM_TRACE",
    priority: "CRITICAL",
    confidence_score: 92,
    status: "FULLY_RECOVERED",
    verified_bytes: 1500,
    reconstructed_bytes: 0,
    missing_bytes: 0,
    reconstruction_method: "CONTIGUOUS",
    validation: { valid: true },
    fragments: [],
    ai_summary: null
  },
  {
    id: "artifact_003",
    filename: "evidence_capture.png",
    mime_type: "image/png",
    category: "PHOTO_MEDIA",
    priority: "HIGH",
    confidence_score: 34,
    status: "CORRUPTED",
    verified_bytes: 2000,
    reconstructed_bytes: 1000,
    missing_bytes: 500,
    reconstruction_method: "NONE",
    validation: { valid: false, error: "declared chunk exceeds remaining evidence" },
    fragments: [],
    ai_summary: null
  },
  {
    id: "artifact_004",
    filename: "damaged_sector.txt",
    mime_type: "text/plain",
    category: "DOCUMENT",
    priority: "LOW",
    confidence_score: 12,
    status: "UNRECOVERABLE",
    verified_bytes: 100,
    reconstructed_bytes: 0,
    missing_bytes: 900,
    reconstruction_method: "NONE",
    validation: { valid: false, error: "no valid header found" },
    fragments: [],
    ai_summary: null
  }
];

export const mockCase: Case = {
  id: "case_001",
  name: "Operation Phantom",
  description: "Investigation into unauthorized access.",
  artifacts: mockArtifacts
};

export async function fetchCase(): Promise<Case> {
  return mockCase;
}

export async function fetchArtifacts(): Promise<Artifact[]> {
  return mockArtifacts;
}

export async function fetchArtifactById(id: string): Promise<Artifact | undefined> {
  return mockArtifacts.find(a => a.id === id);
}

export async function fetchArtifactExplanation(id: string) {
  const artifact = await fetchArtifactById(id);
  return artifact?.ai_summary;
}
