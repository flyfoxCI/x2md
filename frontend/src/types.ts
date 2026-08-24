export type ImportStatus = "ready" | "partial" | "blocked";
export type ArtifactKind = "translation" | "summary" | "skill" | "research" | "user_edit";
export type DerivationKind = Exclude<ArtifactKind, "research" | "user_edit">;
export type SourcePlatform =
  | "web"
  | "github"
  | "arxiv"
  | "huggingface"
  | "youtube"
  | "x";

export interface Source {
  id: number;
  canonical_url: string;
  platform: SourcePlatform | string;
  title: string;
  author: string | null;
  published_at: string | null;
  raw_text: string;
  source_markdown: string;
  metadata_json: Record<string, unknown>;
  import_status: ImportStatus;
  failure_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface SourcePage {
  items: Source[];
  total: number;
  page: number;
  page_size: number;
}

export interface Artifact {
  id: number;
  source_id: number;
  kind: ArtifactKind;
  title: string;
  markdown: string;
  language: string | null;
  parent_artifact_id: number | null;
  research_run_id?: number | null;
  model_metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SourceDetail {
  source: Source;
  artifacts: Artifact[];
  research_runs?: ResearchRun[];
  tag_assignments?: TagAssignment[];
}

export type ResearchRunStatus = "queued" | "running" | "completed" | "partial" | "blocked" | "failed";

export interface ResearchRun {
  id: number;
  source_id: number;
  trigger: string;
  status: ResearchRunStatus;
  phase: string | null;
  budget_json: Record<string, unknown>;
  coverage_json: Record<string, unknown>;
  attempt_count: number;
  max_attempts: number;
  next_attempt_at: string | null;
  failure_code: string | null;
  provider_metadata_json: Record<string, unknown>;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResearchEvidence {
  id: number;
  research_run_id: number;
  source_id: number;
  locator: string;
  kind: string;
  title: string | null;
  ordinal: number;
  source_revision: string | null;
  content: string | null;
  digest_markdown: string | null;
  status: "included" | "excluded" | string;
  exclusion_reason: string | null;
  created_at: string;
}

export interface ResearchEvidencePage {
  items: ResearchEvidence[];
  total: number;
  page: number;
  page_size: number;
}

export interface TagDefinition {
  id: number;
  slug: string;
  label: string;
  facet: string | null;
  parent_id: number | null;
  is_system: boolean;
  description: string | null;
  created_at: string;
}

export interface TagAssignment {
  id: number;
  source_id: number;
  research_run_id: number | null;
  tag_id: number;
  origin: string;
  status: "suggested" | "accepted" | "rejected" | string;
  confidence: number | null;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  source_id: number;
  artifact_id: number | null;
  url: string;
  section: string;
}

export interface ChatTurn {
  id: number;
  source_id: number;
  question: string;
  answer_markdown: string;
  citations_json: Citation[];
  created_at: string;
}

export interface PresentationSettings {
  theme: "system" | "light" | "dark";
  preview_device: "desktop" | "mobile";
}

export interface Settings {
  aiConfigured: boolean;
  presentation: PresentationSettings;
  research?: { autoStart: boolean };
}

export interface ApiError {
  code: string;
  message: string;
  status?: number;
}

export interface AuthenticatedUser {
  id: number;
  username: string;
}

export interface AuthenticatedSession {
  user: AuthenticatedUser;
  csrfToken: string;
}

export interface SourceQuery {
  q?: string;
  platform?: string;
  tag?: string;
  page?: number;
  page_size?: number;
}

export interface ArtifactEdit {
  title?: string;
  markdown: string;
  language?: string;
}
