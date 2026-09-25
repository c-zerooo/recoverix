export type ArtifactCategory = 'DOCUMENT' | 'DATABASE_LOG' | 'PHOTO_MEDIA' | 'SYSTEM_TRACE' | 'BINARY_ARCHIVE';
export type PriorityLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
export type RecoveryStatus = 'FULLY_RECOVERED' | 'PARTIALLY_RECOVERED' | 'CORRUPTED' | 'UNRECOVERABLE';
export type ReconstructionMethod = 'CONTIGUOUS' | 'BIFRAGMENT_GAP' | 'NONE';

/**
 * Deterministic 100-point rubric breakdown.
 * Note: These status thresholds (85-100: FULLY_RECOVERED, 50-84: PARTIALLY_RECOVERED, 
 * 20-49: CORRUPTED, 0-19: UNRECOVERABLE) are our prototype policy, 
 * not an established forensic standard.
 */
export interface ConfidenceBreakdown {
  header_validity: number; // max 20
  footer_validity: number; // max 20
  structural_validation: number; // max 30
  size_plausibility: number; // max 15
  reconstruction_integrity: number; // max 15
  total: number; // max 100
}

export interface ValidationCheck {
  name: string;
  detail: string;
  passed: boolean;
}

export interface ValidationResult {
  valid: boolean;
  error?: string;
  checks?: ValidationCheck[];
}

export type FragmentType = 'VERIFIED' | 'RECONSTRUCTED_GAP' | 'MISSING';

export interface Fragment {
  id: string;
  start_offset: number;
  end_offset: number;
  type: FragmentType;
  source_disk?: string;
}

export interface AIExplanation {
  summary: string;
  details: string[];
  cached?: boolean;
}

export interface Artifact {
  id: string;
  filename: string;
  mime_type: string;
  category: ArtifactCategory;
  priority: PriorityLevel;
  confidence_score: number;
  confidence_breakdown: ConfidenceBreakdown;
  status: RecoveryStatus;
  verified_bytes: number;
  reconstructed_bytes: number;
  missing_bytes: number;
  reconstruction_method: ReconstructionMethod;
  validation: ValidationResult;
  fragments: Fragment[];
  preview_text: string;
  ai_summary: AIExplanation | null;
}

export interface Case {
  id: string;
  name: string;
  description: string;
  artifacts: Artifact[];
}

export interface GroundTruthExpectedArtifact {
  id: string;
  filename: string;
  scenario: 'CLEAN_CONTIGUOUS' | 'DELETED' | 'FRAGMENTED' | 'BIFRAGMENT_GAP' | 'CORRUPTED' | 'UNRECOVERABLE';
  expected_status: RecoveryStatus;
  original_sha256: string;
  total_bytes: number;
}

export interface GroundTruth {
  case_id: string;
  image_filename: string;
  expected_artifacts: GroundTruthExpectedArtifact[];
}
