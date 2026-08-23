import { useCallback, useEffect, useRef, useState } from "react";

import {
  deriveSource,
  editArtifact,
  getSource,
  getSettings,
  importSource,
  isAbortError,
  isApiError,
  listSources,
  updateSettings,
} from "./api";
import { AppHeader } from "./components/AppHeader";
import { EditorWorkspace, type WorkspaceTab } from "./components/EditorWorkspace";
import { ImportDialog } from "./components/ImportDialog";
import { KnowledgeSidebar } from "./components/KnowledgeSidebar";
import { PreviewPanel } from "./components/PreviewPanel";
import { StatusMessage } from "./components/StatusMessage";
import type { ApiError, Artifact, DerivationKind, PresentationSettings, Source, SourceDetail } from "./types";
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

function App() {
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
          && !samePresentation(desiredPresentationRef.current, requestedPresentation)
        ) {
          flushPresentationSaveRef.current();
        }
      });
  }, [applyPresentation]);

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
        return;
      }
      setDetail(loaded);
    } catch (reason) {
      if (controller.signal.aborted || requestId !== detailRequestIdRef.current || isAbortError(reason)) {
        return;
      }
      setDetail(null);
      setError(asApiError(reason));
    } finally {
      if (requestId === detailRequestIdRef.current) {
        setDetailLoading(false);
      }
    }
  }, []);

  const loadSources = useCallback(async (search = "", signal?: AbortSignal) => {
    setLibraryLoading(true);
    try {
      const page = await listSources(search.trim() ? { q: search.trim() } : {}, signal);
      setSources(page.items);
      setTotal(page.total);
    } catch (reason) {
      if (!isAbortError(reason)) {
        setError(asApiError(reason));
      }
    } finally {
      if (!signal?.aborted) {
        setLibraryLoading(false);
      }
    }
  }, []);

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
        if (!controller.signal.aborted && !isAbortError(reason)) {
          setPresentationError("显示设置无法加载，已使用默认设置。");
        }
      });
    return () => controller.abort();
  }, [applyPresentation]);

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
      await loadSources(query);
      await loadDetail(imported);
      setSuccess("来源已导入并保存到知识库");
    } catch (reason) {
      setError(asApiError(reason));
    } finally {
      setImporting(false);
    }
  }

  async function handleDerive(kind: DerivationKind) {
    const actionSource = selectedSourceRef.current;
    if (!actionSource || derivingBySourceId[actionSource.id]) return;
    const tabByKind: Record<DerivationKind, WorkspaceTab> = {
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
      await loadDetail(actionSource);
      if (selectedSourceRef.current?.id === actionSource.id) {
        setSuccess("已生成新的知识版本");
      }
    } catch (reason) {
      if (selectedSourceRef.current?.id === actionSource.id) {
        setError(asApiError(reason));
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
      await loadDetail(actionSource);
      if (selectedSourceRef.current?.id === actionSource.id) {
        setSuccess("已保存为新版本");
      }
    } catch (reason) {
      if (selectedSourceRef.current?.id === actionSource.id) {
        setError(asApiError(reason));
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
        onUrlChange={setUrl}
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
    </main>
  );
}

export default App;
