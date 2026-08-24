import type {
  AuthenticatedSession,
  AuthenticatedUser,
  ApiError,
  Artifact,
  ArtifactEdit,
  DerivationKind,
  ChatTurn,
  ResearchEvidence,
  ResearchEvidencePage,
  ResearchRun,
  Settings,
  Source,
  SourceDetail,
  SourcePage,
  SourceQuery,
  TagAssignment,
  TagDefinition,
} from "./types";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
const apiBaseUrl = (configuredBaseUrl || "/api").replace(/\/$/, "");

interface BackendErrorEnvelope {
  detail: {
    code?: unknown;
    message?: unknown;
  };
}

interface RequestOptions extends RequestInit {
  signal?: AbortSignal;
}

type ResponseGuard<T> = (value: unknown) => value is T;

let currentCsrfToken: string | undefined;
let credentialGeneration = 0;
let authenticationIntent = 0;
let authMutationQueue: Promise<void> = Promise.resolve();

interface ParsedResponse {
  response: Response;
  text: string;
  payload: unknown;
}

export function normalizeApiError(
  error: unknown,
  status?: number,
): ApiError {
  if (isApiError(error)) {
    return { ...error, status: error.status ?? status };
  }

  if (isBackendErrorEnvelope(error)) {
    return {
      code: typeof error.detail.code === "string" ? error.detail.code : "request_failed",
      message:
        typeof error.detail.message === "string"
          ? error.detail.message
          : "请求未能完成，请稍后重试。",
      status,
    };
  }

  return {
    code: "network_error",
    message: "无法连接到知识库服务，请确认服务正在运行。",
    status,
  };
}

export function isApiError(error: unknown): error is ApiError {
  return (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof error.code === "string" &&
    "message" in error &&
    typeof error.message === "string"
  );
}

function isBackendErrorEnvelope(value: unknown): value is BackendErrorEnvelope {
  return (
    typeof value === "object" &&
    value !== null &&
    "detail" in value &&
    typeof value.detail === "object" &&
    value.detail !== null
  );
}

function isAuthenticationRequiredEnvelope(value: unknown): value is BackendErrorEnvelope {
  return (
    isBackendErrorEnvelope(value) &&
    value.detail.code === "authentication_required" &&
    typeof value.detail.message === "string"
  );
}

function path(pathname: string): string {
  return `${apiBaseUrl}${pathname}`;
}

function invalidResponse(status: number): ApiError {
  return {
    code: "invalid_response",
    message: "服务返回的数据格式无效，请稍后重试。",
    status,
  };
}

function requestFailed(status: number): ApiError {
  return {
    code: "request_failed",
    message: "知识库服务暂时无法完成请求，请稍后重试。",
    status,
  };
}

async function request<T>(
  pathname: string,
  guard: ResponseGuard<T>,
  init?: RequestOptions,
): Promise<T> {
  const requestGeneration = captureCredentialGeneration();
  const parsed = await receiveResponse(pathname, init);
  throwForFailedResponse(parsed, requestGeneration);
  if (parsed.payload === undefined || !guard(parsed.payload)) {
    throw invalidResponse(parsed.response.status);
  }
  return parsed.payload;
}

async function requestNoContent(
  pathname: string,
  init: RequestOptions,
  requestGeneration: number,
): Promise<void> {
  const parsed = await receiveResponse(pathname, init);
  throwForFailedResponse(parsed, requestGeneration);
  if (parsed.response.status !== 204 || parsed.text !== "") {
    throw invalidResponse(parsed.response.status);
  }
}

async function receiveResponse(pathname: string, init?: RequestOptions): Promise<ParsedResponse> {
  const response = await fetchResponse(pathname, init);
  let text: string;
  try {
    text = await response.text();
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw response.ok ? invalidResponse(response.status) : requestFailed(response.status);
  }
  return {
    response,
    text,
    payload: text ? safelyParseJson(text) : undefined,
  };
}

function throwForFailedResponse(parsed: ParsedResponse, requestGeneration: number): void {
  if (parsed.response.ok) {
    return;
  }
  if (
    parsed.response.status === 401 &&
    isAuthenticationRequiredEnvelope(parsed.payload)
  ) {
    clearAuthenticationIfCurrent(requestGeneration);
  }
  throw isBackendErrorEnvelope(parsed.payload)
    ? normalizeApiError(parsed.payload, parsed.response.status)
    : requestFailed(parsed.response.status);
}

async function fetchResponse(pathname: string, init?: RequestOptions): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(path(pathname), {
      ...init,
      credentials: "same-origin",
      headers: requestHeaders(init),
    });
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw normalizeApiError(error);
  }

  return response;
}

function requestHeaders(init?: RequestOptions): Headers {
  const headers = new Headers(init?.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  headers.delete("X-CSRF-Token");
  if (currentCsrfToken && isUnsafeMethod(init?.method)) {
    headers.set("X-CSRF-Token", currentCsrfToken);
  }
  return headers;
}

function isUnsafeMethod(method?: string): boolean {
  const normalizedMethod = method?.toUpperCase() || "GET";
  return (
    normalizedMethod === "POST" ||
    normalizedMethod === "PATCH" ||
    normalizedMethod === "PUT" ||
    normalizedMethod === "DELETE"
  );
}

function safelyParseJson(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return undefined;
  }
}

export function isAbortError(error: unknown): boolean {
  return isRecord(error) && error.name === "AbortError";
}

function queryString(query: SourceQuery): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== "") {
      search.set(key, String(value));
    }
  }
  const serialized = search.toString();
  return serialized ? `?${serialized}` : "";
}

function isSource(value: unknown): value is Source {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "number" &&
    typeof value.canonical_url === "string" &&
    typeof value.platform === "string" &&
    typeof value.title === "string" &&
    nullableString(value.author) &&
    nullableString(value.published_at) &&
    typeof value.raw_text === "string" &&
    typeof value.source_markdown === "string" &&
    isRecord(value.metadata_json) &&
    isImportStatus(value.import_status) &&
    nullableString(value.failure_reason) &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string"
  );
}

function isSourcePage(value: unknown): value is SourcePage {
  if (!isRecord(value)) {
    return false;
  }

  return (
    Array.isArray(value.items) &&
    value.items.every(isSource) &&
    typeof value.total === "number" &&
    typeof value.page === "number" &&
    typeof value.page_size === "number"
  );
}

function isArtifact(value: unknown): value is Artifact {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "number" &&
    typeof value.source_id === "number" &&
    isArtifactKind(value.kind) &&
    typeof value.title === "string" &&
    typeof value.markdown === "string" &&
    nullableString(value.language) &&
    nullableNumber(value.parent_artifact_id) &&
    (!Object.hasOwn(value, "research_run_id") || nullableNumber(value.research_run_id)) &&
    isRecord(value.model_metadata_json) &&
    typeof value.created_at === "string" &&
    typeof value.updated_at === "string"
  );
}

function isSourceDetail(value: unknown): value is SourceDetail {
  return (
    isRecord(value) &&
    isSource(value.source) &&
    Array.isArray(value.artifacts) &&
    value.artifacts.every(isArtifact) &&
    (!Object.hasOwn(value, "research_runs") || (Array.isArray(value.research_runs) && value.research_runs.every(isResearchRun))) &&
    (!Object.hasOwn(value, "tag_assignments") || (Array.isArray(value.tag_assignments) && value.tag_assignments.every(isTagAssignment)))
  );
}

function isChatTurn(value: unknown): value is ChatTurn {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "number" &&
    typeof value.source_id === "number" &&
    typeof value.question === "string" &&
    typeof value.answer_markdown === "string" &&
    Array.isArray(value.citations_json) &&
    value.citations_json.every(isCitation) &&
    typeof value.created_at === "string"
  );
}

function isSettings(value: unknown): value is Settings {
  if (!isRecord(value) || !isRecord(value.presentation)) {
    return false;
  }

  return (
    typeof value.aiConfigured === "boolean" &&
    (value.presentation.theme === "system" ||
      value.presentation.theme === "light" ||
      value.presentation.theme === "dark") &&
    (value.presentation.preview_device === "desktop" ||
      value.presentation.preview_device === "mobile")
  );
}

function isResearchRun(value: unknown): value is ResearchRun {
  return isRecord(value)
    && typeof value.id === "number"
    && typeof value.source_id === "number"
    && typeof value.trigger === "string"
    && isResearchRunStatus(value.status)
    && nullableString(value.phase)
    && isRecord(value.budget_json)
    && isRecord(value.coverage_json)
    && typeof value.attempt_count === "number"
    && typeof value.max_attempts === "number"
    && nullableString(value.next_attempt_at)
    && nullableString(value.failure_code)
    && isRecord(value.provider_metadata_json)
    && nullableString(value.started_at)
    && nullableString(value.finished_at)
    && typeof value.created_at === "string"
    && typeof value.updated_at === "string";
}

function isResearchEvidence(value: unknown): value is ResearchEvidence {
  return isRecord(value)
    && typeof value.id === "number"
    && typeof value.research_run_id === "number"
    && typeof value.source_id === "number"
    && typeof value.locator === "string"
    && typeof value.kind === "string"
    && nullableString(value.title)
    && typeof value.ordinal === "number"
    && nullableString(value.source_revision)
    && nullableString(value.content)
    && nullableString(value.digest_markdown)
    && typeof value.status === "string"
    && nullableString(value.exclusion_reason)
    && typeof value.created_at === "string";
}

function isResearchEvidencePage(value: unknown): value is ResearchEvidencePage {
  return isRecord(value)
    && Array.isArray(value.items)
    && value.items.every(isResearchEvidence)
    && typeof value.total === "number"
    && typeof value.page === "number"
    && typeof value.page_size === "number";
}

function isTagDefinition(value: unknown): value is TagDefinition {
  return isRecord(value)
    && typeof value.id === "number"
    && typeof value.slug === "string"
    && typeof value.label === "string"
    && nullableString(value.facet)
    && nullableNumber(value.parent_id)
    && typeof value.is_system === "boolean"
    && nullableString(value.description)
    && typeof value.created_at === "string";
}

function isTagAssignment(value: unknown): value is TagAssignment {
  return isRecord(value)
    && typeof value.id === "number"
    && typeof value.source_id === "number"
    && nullableNumber(value.research_run_id)
    && typeof value.tag_id === "number"
    && typeof value.origin === "string"
    && typeof value.status === "string"
    && nullableNumber(value.confidence)
    && typeof value.created_at === "string"
    && typeof value.updated_at === "string";
}

function isResearchRunStatus(value: unknown): value is ResearchRun["status"] {
  return value === "queued" || value === "running" || value === "completed"
    || value === "partial" || value === "blocked" || value === "failed";
}

function isCitation(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value.source_id === "number" &&
    nullableNumber(value.artifact_id) &&
    typeof value.url === "string" &&
    typeof value.section === "string"
  );
}

function nullableString(value: unknown): value is string | null {
  return typeof value === "string" || value === null;
}

function nullableNumber(value: unknown): value is number | null {
  return typeof value === "number" || value === null;
}

function isImportStatus(value: unknown): value is Source["import_status"] {
  return value === "ready" || value === "partial" || value === "blocked";
}

function isArtifactKind(value: unknown): value is Artifact["kind"] {
  return (
    value === "translation" ||
    value === "summary" ||
    value === "skill" ||
    value === "research" ||
    value === "user_edit"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isAuthenticatedUser(value: unknown): value is AuthenticatedUser {
  return (
    isRecord(value) &&
    typeof value.id === "number" &&
    Number.isInteger(value.id) &&
    value.id > 0 &&
    typeof value.username === "string" &&
    value.username.length > 0
  );
}

function isAuthenticatedSession(value: unknown): value is AuthenticatedSession {
  return (
    isRecord(value) &&
    isAuthenticatedUser(value.user) &&
    typeof value.csrfToken === "string" &&
    value.csrfToken.length > 0
  );
}

export function clearAuthentication(): void {
  clearCredentials();
  authenticationIntent += 1;
}

function clearCredentials(): void {
  currentCsrfToken = undefined;
  credentialGeneration += 1;
}

function captureCredentialGeneration(): number {
  return credentialGeneration;
}

function clearAuthenticationIfCurrent(requestGeneration: number): void {
  if (credentialGeneration === requestGeneration) {
    clearCredentials();
  }
}

function captureAuthenticationIntent(): number {
  return authenticationIntent;
}

function reserveAuthenticationMutation(): number {
  authenticationIntent += 1;
  return authenticationIntent;
}

function installSerializedMutationSession(session: AuthenticatedSession): AuthenticatedSession {
  currentCsrfToken = session.csrfToken;
  credentialGeneration += 1;
  return session;
}

function installSessionReadIfCurrent(
  session: AuthenticatedSession,
  authenticationIntentAtStart: number,
  credentialGenerationAtStart: number,
): AuthenticatedSession {
  if (
    authenticationIntent === authenticationIntentAtStart &&
    credentialGeneration === credentialGenerationAtStart
  ) {
    return installSerializedMutationSession(session);
  }
  return session;
}

function enqueueAuthMutation<T>(operation: () => Promise<T>): Promise<T> {
  const result = authMutationQueue.then(operation);
  authMutationQueue = result.then(
    () => undefined,
    () => undefined,
  );
  return result;
}

export async function getCurrentSession(
  signal?: AbortSignal,
): Promise<AuthenticatedSession> {
  const authenticationIntentAtStart = captureAuthenticationIntent();
  const credentialGenerationAtStart = captureCredentialGeneration();
  return installSessionReadIfCurrent(
    await request("/auth/me", isAuthenticatedSession, { signal }),
    authenticationIntentAtStart,
    credentialGenerationAtStart,
  );
}

export function login(
  username: string,
  password: string,
): Promise<AuthenticatedSession> {
  reserveAuthenticationMutation();
  return enqueueAuthMutation(async () =>
    installSerializedMutationSession(
      await request("/auth/login", isAuthenticatedSession, {
        method: "POST",
        body: JSON.stringify({ username, password }),
      }),
    ),
  );
}

export function logout(): Promise<void> {
  reserveAuthenticationMutation();
  return enqueueAuthMutation(async () => {
    const requestGeneration = captureCredentialGeneration();
    try {
      await requestNoContent("/auth/logout", { method: "POST" }, requestGeneration);
    } finally {
      clearAuthenticationIfCurrent(requestGeneration);
    }
  });
}

export function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<AuthenticatedSession> {
  reserveAuthenticationMutation();
  return enqueueAuthMutation(async () =>
    installSerializedMutationSession(
      await request("/auth/change-password", isAuthenticatedSession, {
        method: "POST",
        body: JSON.stringify({ currentPassword, newPassword }),
      }),
    ),
  );
}

export async function listSources(
  query: SourceQuery = {},
  signal?: AbortSignal,
): Promise<SourcePage> {
  return request(`/sources${queryString(query)}`, isSourcePage, { signal });
}

export function importSource(url: string): Promise<Source> {
  return request("/imports", isSource, {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export function getSource(
  sourceId: number,
  signal?: AbortSignal,
): Promise<SourceDetail> {
  return request(`/sources/${sourceId}`, isSourceDetail, { signal });
}

export function startResearch(sourceId: number, signal?: AbortSignal): Promise<ResearchRun> {
  return request(`/sources/${sourceId}/research`, isResearchRun, {
    method: "POST",
    signal,
  });
}

export function getResearchRun(runId: number, signal?: AbortSignal): Promise<ResearchRun> {
  return request(`/research-runs/${runId}`, isResearchRun, { signal });
}

export function listResearchEvidence(
  runId: number,
  page = 1,
  pageSize = 20,
  signal?: AbortSignal,
): Promise<ResearchEvidencePage> {
  return request(
    `/research-runs/${runId}/evidence?page=${page}&page_size=${pageSize}`,
    isResearchEvidencePage,
    { signal },
  );
}

export function listTags(signal?: AbortSignal): Promise<{ items: TagDefinition[] }> {
  return request("/tags", (value): value is { items: TagDefinition[] } => (
    isRecord(value) && Array.isArray(value.items) && value.items.every(isTagDefinition)
  ), { signal });
}

export function createCustomTag(sourceId: number, label: string): Promise<TagAssignment> {
  return request(`/sources/${sourceId}/tags`, isTagAssignment, {
    method: "POST",
    body: JSON.stringify({ label }),
  });
}

export function updateTagAssignment(
  assignmentId: number,
  status: "accepted" | "rejected",
): Promise<TagAssignment> {
  return request(`/tag-assignments/${assignmentId}`, isTagAssignment, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export async function deleteTagAssignment(assignmentId: number): Promise<void> {
  let response: Response;
  try {
    response = await fetch(path(`/tag-assignments/${assignmentId}`), {
      method: "DELETE",
      headers: { Accept: "application/json" },
    });
  } catch (error) {
    throw normalizeApiError(error);
  }
  if (!response.ok) {
    const payload = safelyParseJson(await response.text());
    throw isBackendErrorEnvelope(payload)
      ? normalizeApiError(payload, response.status)
      : requestFailed(response.status);
  }
}

export function deriveSource(
  sourceId: number,
  kind: DerivationKind,
): Promise<Artifact> {
  return request(`/sources/${sourceId}/derive`, isArtifact, {
    method: "POST",
    body: JSON.stringify({ kind }),
  });
}

export function editArtifact(
  artifactId: number,
  edit: ArtifactEdit,
): Promise<Artifact> {
  return request(`/artifacts/${artifactId}`, isArtifact, {
    method: "PATCH",
    body: JSON.stringify(edit),
  });
}

export function chatWithSource(
  sourceId: number,
  question: string,
  signal?: AbortSignal,
): Promise<ChatTurn> {
  return request(`/sources/${sourceId}/chat`, isChatTurn, {
    method: "POST",
    body: JSON.stringify({ question }),
    signal,
  });
}

export function getSettings(signal?: AbortSignal): Promise<Settings> {
  return request("/settings", isSettings, { signal });
}

export function updateSettings(
  settings: Settings["presentation"],
  signal?: AbortSignal,
): Promise<Settings> {
  return request("/settings", isSettings, {
    method: "PATCH",
    body: JSON.stringify({ presentation: settings }),
    signal,
  });
}

export function updateResearchSettings(
  autoStart: boolean,
  signal?: AbortSignal,
): Promise<Settings> {
  return request("/settings", isSettings, {
    method: "PATCH",
    body: JSON.stringify({ research: { autoStart } }),
    signal,
  });
}

export function artifactDownloadUrl(artifactId: number): string {
  return path(`/artifacts/${artifactId}/download`);
}
