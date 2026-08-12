import { useCallback, useEffect, useRef, useState } from "react";

import {
  deriveSource,
  editArtifact,
  getSource,
  importSource,
  isAbortError,
  isApiError,
  listSources,
} from "./api";
import { AppHeader } from "./components/AppHeader";
import { EditorWorkspace, type WorkspaceTab } from "./components/EditorWorkspace";
import { ImportDialog } from "./components/ImportDialog";
import { KnowledgeSidebar } from "./components/KnowledgeSidebar";
import { PreviewPanel } from "./components/PreviewPanel";
import { StatusMessage } from "./components/StatusMessage";
import type { ApiError, Artifact, ArtifactKind, Source, SourceDetail } from "./types";
import "./styles/app.css";
import "./styles/tokens.css";
import "./styles/workspace.css";

const compactViewportQuery = "(max-width: 720px)";

const defaultError: ApiError = {
  code: "network_error",
  message: "无法连接到知识库服务，请确认服务正在运行。",
};

function asApiError(reason: unknown): ApiError {
  return isApiError(reason) ? reason : defaultError;
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
  const detailRequestRef = useRef<AbortController | null>(null);
  const detailRequestIdRef = useRef(0);
  const importTriggerRef = useRef<HTMLButtonElement | null>(null);
  const libraryTriggerRef = useRef<HTMLButtonElement | null>(null);
  const selectedSourceRef = useRef<Source | null>(null);
  const restoreImportFocusRef = useRef(false);
  const isCompactViewport = useMediaQuery(compactViewportQuery);

  const handleContentChange = useCallback((markdown: string, artifact: Artifact | null) => {
    setCurrentMarkdown(markdown);
    setSelectedArtifact(artifact);
  }, []);

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
        <PreviewPanel artifact={selectedArtifact} markdown={currentMarkdown} />
      </div>
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
