export type ImportStatus = "ready" | "partial" | "blocked";
export type ArtifactKind = "translation" | "summary" | "skill" | "user_edit";
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
  model_metadata_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SourceDetail {
  source: Source;
  artifacts: Artifact[];
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
