export type ArtifactCategory = 'DOCUMENT' | 'DATABASE_LOG' | 'PHOTO_MEDIA' | 'SYSTEM_TRACE' | 'BINARY_ARCHIVE';
export type PriorityLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
export type RecoveryStatus = 'FULLY_RECOVERED' | 'PARTIALLY_RECOVERED' | 'CORRUPTED' | 'UNRECOVERABLE';
export type ReconstructionMethod = 'CONTIGUOUS' | 'BIFRAGMENT_GAP' | 'NONE';

export interface ConfidenceBreakdown {
  header_validity: number;
  footer_validity: number;
  structural_validation: number;
  size_plausibility: number;
  reconstruction_integrity: number;
  total: number;
}

export interface ValidationResult {
  valid: boolean;
  error?: string;
}

export interface Fragment {
  id: string;
  start_offset: number;
  end_offset: number;
  source_disk: string;
}

export interface AIExplanation {
  summary: string;
  details: string[];
}

export interface Artifact {
  id: string;
  filename: string;
  mime_type: string;
  category: ArtifactCategory;
  priority: PriorityLevel;
  confidence_score: number;
  status: RecoveryStatus;
  verified_bytes: number;
  reconstructed_bytes: number;
  missing_bytes: number;
  reconstruction_method: ReconstructionMethod;
  validation: ValidationResult;
  fragments: Fragment[];
  ai_summary: AIExplanation | null;
}

export interface Case {
  id: string;
  name: string;
  description: string;
  artifacts: Artifact[];
}
