import { useCallback, useEffect, useRef, useState } from "react";

import {
  changePassword,
  clearAuthentication,
  deriveSource,
  editArtifact,
  getCurrentSession,
  getSource,
  getSettings,
  importSource,
  isAbortError,
  isApiError,
  listSources,
  login,
  logout,
  updateSettings,
} from "./api";
import { AccountDialog } from "./components/AccountDialog";
import { AppHeader } from "./components/AppHeader";
import { EditorWorkspace, type WorkspaceTab } from "./components/EditorWorkspace";
import { ImportDialog } from "./components/ImportDialog";
import { KnowledgeSidebar } from "./components/KnowledgeSidebar";
import { LoginScreen } from "./components/LoginScreen";
import { PreviewPanel } from "./components/PreviewPanel";
import { StatusMessage } from "./components/StatusMessage";
import type {
  ApiError,
  Artifact,
  ArtifactKind,
  AuthenticatedSession,
  PresentationSettings,
  Source,
  SourceDetail,
} from "./types";
import "./styles/app.css";
import "./styles/tokens.css";
import "./styles/workspace.css";

const compactViewportQuery = "(max-width: 720px)";
const previewOverlayViewportQuery = "(max-width: 1120px)";

const defaultError: ApiError = {
  code: "network_error",
  message: "无法连接到知识库服务，请确认服务正在运行。",
};

const defaultPresentation: PresentationSettings = {
  theme: "system",
  preview_device: "desktop",
};

const presentationSaveMaxAttempts = 3;
const presentationSaveRetryDelayMs = 500;

function asApiError(reason: unknown): ApiError {
  return isApiError(reason) ? reason : defaultError;
}

function isAuthenticationRequired(reason: unknown): boolean {
  return isApiError(reason) && reason.code === "authentication_required";
}

function samePresentation(left: PresentationSettings, right: PresentationSettings): boolean {
  return left.theme === right.theme && left.preview_device === right.preview_device;
}

function useMediaQuery(query: string) {
  const getMatches = () => (
    typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia(query).matches
  );
  const [matches, setMatches] = useState(getMatches);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return undefined;
    }

    const mediaQuery = window.matchMedia(query);
    const updateMatches = () => setMatches(mediaQuery.matches);
    updateMatches();

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", updateMatches);
      return () => mediaQuery.removeEventListener("change", updateMatches);
    }

    mediaQuery.addListener(updateMatches);
    return () => mediaQuery.removeListener(updateMatches);
  }, [query]);

  return matches;
}

interface AuthenticatedStudioProps {
  session: AuthenticatedSession;
  sessionGeneration: number;
  onAuthenticationRequired: (sessionGeneration: number) => boolean;
  onChangePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  onLogout: () => Promise<void>;
}

function AuthenticatedStudio({
  session,
  sessionGeneration,
  onAuthenticationRequired,
  onChangePassword,
  onLogout,
}: AuthenticatedStudioProps) {
  const [sources, setSources] = useState<Source[]>([]);
  const [total, setTotal] = useState(0);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [selectedSource, setSelectedSource] = useState<Source | null>(null);
  const [detail, setDetail] = useState<SourceDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [url, setUrl] = useState("");
  const [importing, setImporting] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [accountDialogOpen, setAccountDialogOpen] = useState(false);
  const [mobileLibraryOpen, setMobileLibraryOpen] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [derivingBySourceId, setDerivingBySourceId] = useState<Record<number, WorkspaceTab | undefined>>({});
  const [savingBySourceId, setSavingBySourceId] = useState<Record<number, true | undefined>>({});
  const [currentMarkdown, setCurrentMarkdown] = useState("");
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [presentation, setPresentation] = useState<PresentationSettings>(defaultPresentation);
  const [presentationError, setPresentationError] = useState<string | null>(null);
  const detailRequestRef = useRef<AbortController | null>(null);
  const detailRequestIdRef = useRef(0);
  const importTriggerRef = useRef<HTMLButtonElement | null>(null);
  const accountTriggerRef = useRef<HTMLButtonElement | null>(null);
  const libraryTriggerRef = useRef<HTMLButtonElement | null>(null);
  const selectedSourceRef = useRef<Source | null>(null);
  const restoreImportFocusRef = useRef(false);
  const settingsRequestRef = useRef<AbortController | null>(null);
  const settingsSaveRef = useRef<AbortController | null>(null);
  const settingsSaveInFlightRef = useRef(false);
  const presentationSaveAttemptRef = useRef(0);
  const presentationRetryTimeoutRef = useRef<number | null>(null);
  const flushPresentationSaveRef = useRef<() => void>(() => undefined);
  const isMountedRef = useRef(false);
  const desiredPresentationRef = useRef<PresentationSettings>(defaultPresentation);
  const presentationDirtyRef = useRef(false);
  const presentationRef = useRef<PresentationSettings>(defaultPresentation);
  const isCompactViewport = useMediaQuery(compactViewportQuery);
  const isPreviewOverlayViewport = useMediaQuery(previewOverlayViewportQuery);

  const handleAuthenticationRequired = useCallback(
    () => onAuthenticationRequired(sessionGeneration),
    [onAuthenticationRequired, sessionGeneration],
  );

  const handleContentChange = useCallback((markdown: string, artifact: Artifact | null) => {
    setCurrentMarkdown(markdown);
    setSelectedArtifact(artifact);
  }, []);

  const applyPresentation = useCallback((nextPresentation: PresentationSettings) => {
    if (samePresentation(presentationRef.current, nextPresentation)) {
      return;
    }
    presentationRef.current = nextPresentation;
    setPresentation(nextPresentation);
  }, []);

  const flushPresentationSave = useCallback(() => {
    if (!isMountedRef.current || settingsSaveInFlightRef.current) {
      return;
    }

    const requestedPresentation = desiredPresentationRef.current;
    const attempt = presentationSaveAttemptRef.current + 1;
    presentationSaveAttemptRef.current = attempt;
    const controller = new AbortController();
    settingsSaveRef.current = controller;
    settingsSaveInFlightRef.current = true;
    let acceptedResponse = false;
    let authenticationFailed = false;
    void updateSettings(requestedPresentation, controller.signal)
      .then((settings) => {
        if (controller.signal.aborted || !isMountedRef.current) {
          return;
        }
        if (samePresentation(desiredPresentationRef.current, requestedPresentation)) {
          acceptedResponse = true;
          desiredPresentationRef.current = settings.presentation;
          applyPresentation(settings.presentation);
          setPresentationError(attempt > 1 ? "显示设置已保存。" : null);
        }
      })
      .catch((reason) => {
        if (isAuthenticationRequired(reason)) {
          authenticationFailed = true;
          handleAuthenticationRequired();
          return;
        }
        if (
          !controller.signal.aborted
          && isMountedRef.current
          && samePresentation(desiredPresentationRef.current, requestedPresentation)
          && !isAbortError(reason)
        ) {
          if (attempt < presentationSaveMaxAttempts) {
            setPresentationError(`显示设置保存失败，正在重试（第 ${attempt}/${presentationSaveMaxAttempts - 1} 次）。`);
            presentationRetryTimeoutRef.current = window.setTimeout(() => {
              presentationRetryTimeoutRef.current = null;
              flushPresentationSaveRef.current();
            }, presentationSaveRetryDelayMs);
          } else {
            setPresentationError("显示设置仍未保存。请再次选择所需显示设置以重试。");
          }
        }
      })
      .finally(() => {
        settingsSaveInFlightRef.current = false;
        if (settingsSaveRef.current === controller) {
          settingsSaveRef.current = null;
        }
        if (
          !controller.signal.aborted
          && isMountedRef.current
          && !acceptedResponse
          && !authenticationFailed
          && !samePresentation(desiredPresentationRef.current, requestedPresentation)
        ) {
          flushPresentationSaveRef.current();
        }
      });
  }, [applyPresentation, handleAuthenticationRequired]);

  flushPresentationSaveRef.current = flushPresentationSave;

  const focusLibraryTrigger = useCallback(() => {
    libraryTriggerRef.current?.focus();
  }, []);

  const openMobileLibrary = useCallback((trigger: HTMLButtonElement) => {
    libraryTriggerRef.current = trigger;
    setMobileLibraryOpen(true);
  }, []);

  const closeMobileLibrary = useCallback(() => {
    // Move focus before hiding the compact sidebar, so aria-hidden never owns it.
    focusLibraryTrigger();
    setMobileLibraryOpen(false);
  }, [focusLibraryTrigger]);

  const loadDetail = useCallback(async (source: Source) => {
    detailRequestRef.current?.abort();
    const controller = new AbortController();
    detailRequestRef.current = controller;
    const requestId = detailRequestIdRef.current + 1;
    detailRequestIdRef.current = requestId;
    selectedSourceRef.current = source;
    setSelectedSource(source);
    setDetail(null);
    setSelectedArtifact(null);
    setCurrentMarkdown("");
    setDetailLoading(true);
    setError(null);
    setSuccess(null);
    try {
      const loaded = await getSource(source.id, controller.signal);
      if (controller.signal.aborted || requestId !== detailRequestIdRef.current) {
        return false;
      }
      setDetail(loaded);
      return true;
    } catch (reason) {
      if (controller.signal.aborted || requestId !== detailRequestIdRef.current || isAbortError(reason)) {
        return false;
      }
      if (isAuthenticationRequired(reason)) {
        handleAuthenticationRequired();
        return false;
      }
      setDetail(null);
      setError(asApiError(reason));
      return false;
    } finally {
      if (requestId === detailRequestIdRef.current) {
        setDetailLoading(false);
      }
    }
  }, [handleAuthenticationRequired]);

  const loadSources = useCallback(async (search = "", signal?: AbortSignal) => {
    setLibraryLoading(true);
    try {
      const page = await listSources(search.trim() ? { q: search.trim() } : {}, signal);
      setSources(page.items);
      setTotal(page.total);
      return true;
    } catch (reason) {
      if (isAuthenticationRequired(reason)) {
        handleAuthenticationRequired();
        return false;
      } else if (!isAbortError(reason)) {
        setError(asApiError(reason));
      }
      return true;
    } finally {
      if (!signal?.aborted) {
        setLibraryLoading(false);
      }
    }
  }, [handleAuthenticationRequired]);

  useEffect(() => {
    const controller = new AbortController();
    void loadSources(query, controller.signal);
    return () => controller.abort();
  }, [loadSources, query]);

  useEffect(() => () => detailRequestRef.current?.abort(), []);

  useEffect(() => {
    document.documentElement.dataset.theme = presentation.theme;
    return () => {
      if (document.documentElement.dataset.theme === presentation.theme) {
        delete document.documentElement.dataset.theme;
      }
    };
  }, [presentation.theme]);

  useEffect(() => {
    const controller = new AbortController();
    settingsRequestRef.current = controller;
    void getSettings(controller.signal)
      .then((settings) => {
        if (!controller.signal.aborted && !presentationDirtyRef.current) {
          applyPresentation(settings.presentation);
        }
      })
      .catch((reason) => {
        if (controller.signal.aborted || isAbortError(reason)) {
          return;
        }
        if (isAuthenticationRequired(reason)) {
          handleAuthenticationRequired();
          return;
        }
        if (!controller.signal.aborted) {
          setPresentationError("显示设置无法加载，已使用默认设置。");
        }
      });
    return () => controller.abort();
  }, [applyPresentation, handleAuthenticationRequired]);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      settingsRequestRef.current?.abort();
      settingsSaveRef.current?.abort();
      if (presentationRetryTimeoutRef.current !== null) {
        window.clearTimeout(presentationRetryTimeoutRef.current);
        presentationRetryTimeoutRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (!dialogOpen && restoreImportFocusRef.current) {
      restoreImportFocusRef.current = false;
      importTriggerRef.current?.focus();
    }
  }, [dialogOpen]);

  const openImportDialog = useCallback((trigger: HTMLButtonElement) => {
    importTriggerRef.current = trigger;
    setDialogOpen(true);
  }, []);

  const closeImportDialog = useCallback(() => {
    restoreImportFocusRef.current = true;
    setDialogOpen(false);
  }, []);

  const openAccountDialog = useCallback((trigger: HTMLButtonElement) => {
    accountTriggerRef.current = trigger;
    setAccountDialogOpen(true);
  }, []);

  const closeAccountDialog = useCallback(() => {
    setAccountDialogOpen(false);
  }, []);

  const handlePresentationChange = useCallback((nextPresentation: PresentationSettings) => {
    presentationDirtyRef.current = true;
    presentationSaveAttemptRef.current = 0;
    if (presentationRetryTimeoutRef.current !== null) {
      window.clearTimeout(presentationRetryTimeoutRef.current);
      presentationRetryTimeoutRef.current = null;
    }
    desiredPresentationRef.current = nextPresentation;
    applyPresentation(nextPresentation);
    setPresentationError(null);
    flushPresentationSaveRef.current();
  }, [applyPresentation]);

  async function handleImport(urlToImport: string = url) {
    const candidate = urlToImport.trim();
    if (!candidate || importing) return;
    setImporting(true);
    setError(null);
    setSuccess(null);
    try {
      const imported = await importSource(candidate);
      setUrl("");
      closeImportDialog();
      if (!await loadSources(query)) {
        return;
      }
      if (!await loadDetail(imported)) {
        return;
      }
      setSuccess("来源已导入并保存到知识库");
    } catch (reason) {
      if (isAuthenticationRequired(reason)) {
        handleAuthenticationRequired();
      } else {
        setError(asApiError(reason));
      }
    } finally {
      setImporting(false);
    }
  }

  async function handleDerive(kind: Exclude<ArtifactKind, "user_edit">) {
    const actionSource = selectedSourceRef.current;
    if (!actionSource || derivingBySourceId[actionSource.id]) return;
    const tabByKind: Record<Exclude<ArtifactKind, "user_edit">, WorkspaceTab> = {
      translation: "translation",
      summary: "summary",
      skill: "skill",
    };
    const actionTab = tabByKind[kind];
    setDerivingBySourceId((current) => ({ ...current, [actionSource.id]: actionTab }));
    setError(null);
    setSuccess(null);
    try {
      await deriveSource(actionSource.id, kind);
      if (selectedSourceRef.current?.id !== actionSource.id) {
        return;
      }
      if (!await loadDetail(actionSource)) {
        return;
      }
      if (selectedSourceRef.current?.id === actionSource.id) {
        setSuccess("已生成新的知识版本");
      }
    } catch (reason) {
      if (selectedSourceRef.current?.id === actionSource.id) {
        if (isAuthenticationRequired(reason)) {
          handleAuthenticationRequired();
        } else {
          setError(asApiError(reason));
        }
      }
    } finally {
      setDerivingBySourceId((current) => {
        const remaining = { ...current };
        delete remaining[actionSource.id];
        return remaining;
      });
    }
  }

  async function handleSave(artifact: Artifact, markdown: string) {
    const actionSource = selectedSourceRef.current;
    if (!actionSource || actionSource.id !== artifact.source_id || savingBySourceId[actionSource.id]) return;
    setSavingBySourceId((current) => ({ ...current, [actionSource.id]: true }));
    setError(null);
    setSuccess(null);
    try {
      const saved = await editArtifact(artifact.id, { markdown });
      if (selectedSourceRef.current?.id !== actionSource.id) {
        return;
      }
      setSelectedArtifact(saved);
      setCurrentMarkdown(saved.markdown);
      if (!await loadDetail(actionSource)) {
        return;
      }
      if (selectedSourceRef.current?.id === actionSource.id) {
        setSuccess("已保存为新版本");
      }
    } catch (reason) {
      if (selectedSourceRef.current?.id === actionSource.id) {
        if (isAuthenticationRequired(reason)) {
          handleAuthenticationRequired();
        } else {
          setError(asApiError(reason));
        }
      }
    } finally {
      setSavingBySourceId((current) => {
        const remaining = { ...current };
        delete remaining[actionSource.id];
        return remaining;
      });
    }
  }

  const statusSource = detail?.source ?? selectedSource;
  const activeDerivation = selectedSource
    ? derivingBySourceId[selectedSource.id] ?? null
    : null;
  const activeSaving = selectedSource
    ? Boolean(savingBySourceId[selectedSource.id])
    : false;

  return (
    <main className="studio-shell">
      <AppHeader
        importing={importing}
        libraryButtonRef={libraryTriggerRef}
        onImport={() => void handleImport()}
        onOpenLibrary={openMobileLibrary}
        onOpenAccount={openAccountDialog}
        onLogout={onLogout}
        onUrlChange={setUrl}
        user={session.user}
        url={url}
      />
      <div className="studio-grid">
        <KnowledgeSidebar
          loading={libraryLoading}
          isCompactViewport={isCompactViewport}
          mobileOpen={mobileLibraryOpen}
          onCloseMobile={closeMobileLibrary}
          onReturnFocus={focusLibraryTrigger}
          onOpenImport={openImportDialog}
          onQueryChange={setQuery}
          onSelect={(source) => void loadDetail(source)}
          query={query}
          selectedSourceId={selectedSource?.id ?? null}
          sources={sources}
          total={total}
        />
        <div className="workspace-column">
          <StatusMessage error={error} source={statusSource} success={success} />
          <EditorWorkspace
            currentMarkdown={currentMarkdown}
            deriving={activeDerivation}
            detail={detail}
            loading={detailLoading}
            onContentChange={handleContentChange}
            onDerive={(kind) => void handleDerive(kind)}
            onSave={(artifact, markdown) => void handleSave(artifact, markdown)}
            saving={activeSaving}
            selectedArtifact={selectedArtifact}
          />
        </div>
        <PreviewPanel
          artifact={selectedArtifact}
          markdown={currentMarkdown}
          onPresentationChange={handlePresentationChange}
          onAuthenticationRequired={handleAuthenticationRequired}
          presentation={presentation}
          isOverlayViewport={isPreviewOverlayViewport}
          source={detail?.source ?? null}
        />
      </div>
      {presentationError ? <p className="presentation-status" role="status">{presentationError}</p> : null}
      <ImportDialog
        importing={importing}
        onClose={closeImportDialog}
        onImport={(dialogUrl) => void handleImport(dialogUrl)}
        open={dialogOpen}
      />
      {accountDialogOpen ? (
        <AccountDialog
          onChangePassword={onChangePassword}
          onClose={closeAccountDialog}
          onLogout={onLogout}
          trigger={accountTriggerRef.current}
          user={session.user}
        />
      ) : null}
    </main>
  );
}

type AuthenticationStatus = "checking" | "anonymous" | "authenticated";

function App() {
  const [status, setStatus] = useState<AuthenticationStatus>("checking");
  const [session, setSession] = useState<AuthenticatedSession | null>(null);
  const [sessionGeneration, setSessionGeneration] = useState(0);
  const [recoveryError, setRecoveryError] = useState<string | null>(null);
  const [recoveryAttempt, setRecoveryAttempt] = useState(0);
  const sessionGenerationRef = useRef(0);

  const advanceSessionGeneration = useCallback(() => {
    const nextSessionGeneration = sessionGenerationRef.current + 1;
    sessionGenerationRef.current = nextSessionGeneration;
    setSessionGeneration(nextSessionGeneration);
  }, []);

  const transitionToAnonymous = useCallback((expectedSessionGeneration: number) => {
    if (sessionGenerationRef.current !== expectedSessionGeneration) {
      return false;
    }
    clearAuthentication();
    advanceSessionGeneration();
    setSession(null);
    setRecoveryError(null);
    setStatus("anonymous");
    return true;
  }, [advanceSessionGeneration]);

  const installSession = useCallback((
    nextSession: AuthenticatedSession,
    expectedSessionGeneration: number,
  ) => {
    if (sessionGenerationRef.current !== expectedSessionGeneration) {
      return false;
    }
    advanceSessionGeneration();
    setSession(nextSession);
    setRecoveryError(null);
    setStatus("authenticated");
    return true;
  }, [advanceSessionGeneration]);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const expectedSessionGeneration = sessionGenerationRef.current;
    void getCurrentSession(controller.signal)
      .then((nextSession) => {
        if (!controller.signal.aborted && active) {
          installSession(nextSession, expectedSessionGeneration);
        }
      })
      .catch((reason) => {
        if (controller.signal.aborted || !active || isAbortError(reason)) {
          return;
        }
        if (isAuthenticationRequired(reason)) {
          transitionToAnonymous(expectedSessionGeneration);
          return;
        }
        if (sessionGenerationRef.current !== expectedSessionGeneration) {
          return;
        }
        setSession(null);
        setRecoveryError("无法恢复登录状态，请检查连接后重试。");
        setStatus("anonymous");
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [installSession, recoveryAttempt, transitionToAnonymous]);

  const handleLogin = useCallback(async (username: string, password: string) => {
    const expectedSessionGeneration = sessionGenerationRef.current;
    const nextSession = await login(username, password);
    installSession(nextSession, expectedSessionGeneration);
  }, [installSession]);

  const handleLogout = useCallback(async () => {
    const expectedSessionGeneration = sessionGenerationRef.current;
    try {
      await logout();
    } finally {
      transitionToAnonymous(expectedSessionGeneration);
    }
  }, [transitionToAnonymous]);

  const handleChangePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    const expectedSessionGeneration = sessionGenerationRef.current;
    try {
      installSession(await changePassword(currentPassword, newPassword), expectedSessionGeneration);
    } catch (reason) {
      if (isAuthenticationRequired(reason)) {
        transitionToAnonymous(expectedSessionGeneration);
      }
      throw reason;
    }
  }, [installSession, transitionToAnonymous]);

  if (status === "checking") {
    return (
      <main className="auth-shell" aria-busy="true">
        <p role="status">正在恢复登录状态…</p>
      </main>
    );
  }

  if (status === "anonymous" || !session) {
    return (
      <LoginScreen
        onLogin={handleLogin}
        onRetrySession={recoveryError ? () => {
          setRecoveryError(null);
          setStatus("checking");
          setRecoveryAttempt((current) => current + 1);
        } : undefined}
        recoveryError={recoveryError}
      />
    );
  }

  return (
    <AuthenticatedStudio
      onAuthenticationRequired={transitionToAnonymous}
      onChangePassword={handleChangePassword}
      onLogout={handleLogout}
      session={session}
      sessionGeneration={sessionGeneration}
    />
  );
}

export default App;
