import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import {
  chatWithSource,
  deriveSource,
  editArtifact,
  getCurrentSession,
  getSettings,
  getSource,
  importSource,
  listSources,
  updateSettings,
} from "../api";
import type { Artifact, AuthenticatedSession, Settings } from "../types";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  getCurrentSession: vi.fn(),
  listSources: vi.fn(),
  importSource: vi.fn(),
  getSource: vi.fn(),
  deriveSource: vi.fn(),
  editArtifact: vi.fn(),
  chatWithSource: vi.fn(),
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
}));

const mockedListSources = vi.mocked(listSources);
const mockedImportSource = vi.mocked(importSource);
const mockedGetSource = vi.mocked(getSource);
const mockedDeriveSource = vi.mocked(deriveSource);
const mockedEditArtifact = vi.mocked(editArtifact);
const mockedChatWithSource = vi.mocked(chatWithSource);
const mockedGetCurrentSession = vi.mocked(getCurrentSession);
const mockedGetSettings = vi.mocked(getSettings);
const mockedUpdateSettings = vi.mocked(updateSettings);

const defaultSettings: Settings = {
  aiConfigured: false,
  presentation: { theme: "system", preview_device: "desktop" },
};

const defaultSession: AuthenticatedSession = {
  user: { id: 1, username: "alice" },
  csrfToken: "csrf-test-token",
};

let compactViewport = false;
const mediaQueryListeners = new Set<(event: MediaQueryListEvent) => void>();

function installMatchMedia() {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockImplementation(() => ({
      get matches() {
        return compactViewport;
      },
      media: "(max-width: 720px)",
      onchange: null,
      addEventListener: (_type: string, listener: EventListenerOrEventListenerObject) => {
        if (typeof listener === "function") {
          mediaQueryListeners.add(listener as (event: MediaQueryListEvent) => void);
        }
      },
      removeEventListener: (_type: string, listener: EventListenerOrEventListenerObject) => {
        if (typeof listener === "function") {
          mediaQueryListeners.delete(listener as (event: MediaQueryListEvent) => void);
        }
      },
      addListener: (listener: (event: MediaQueryListEvent) => void) => mediaQueryListeners.add(listener),
      removeListener: (listener: (event: MediaQueryListEvent) => void) => mediaQueryListeners.delete(listener),
      dispatchEvent: () => true,
    })),
  });
}

async function setCompactViewport(matches: boolean) {
  compactViewport = matches;
  await act(async () => {
    mediaQueryListeners.forEach((listener) => {
      listener({ matches, media: "(max-width: 720px)" } as MediaQueryListEvent);
    });
  });
}

const source = {
  id: 7,
  canonical_url: "https://github.com/example/reasoning",
  platform: "github",
  title: "Reasoning at Scale",
  author: "Ada Lovelace",
  published_at: null,
  raw_text: "Original source text",
  source_markdown: "# Original\n\nOriginal source text",
  metadata_json: {},
  import_status: "ready" as const,
  failure_reason: null,
  created_at: "2026-08-12T00:00:00Z",
  updated_at: "2026-08-12T00:00:00Z",
};

const translation = {
  id: 21,
  source_id: source.id,
  kind: "translation" as const,
  title: "Reasoning at Scale（中文）",
  markdown: "# 中文翻译\n\n用于测试的中文内容。",
  language: "zh",
  parent_artifact_id: null,
  model_metadata_json: {},
  created_at: "2026-08-12T00:00:00Z",
  updated_at: "2026-08-12T00:00:00Z",
};

const skill = {
  ...translation,
  id: 22,
  kind: "skill" as const,
  title: "Reasoning Skill",
  markdown: "# Reasoning Skill\n\n## When to use",
  language: "en",
};

const citedAnswer = {
  id: 44,
  source_id: source.id,
  question: "这个方法什么时候适用？",
  answer_markdown: "当问题需要分步验证时适用。",
  citations_json: [
    {
      source_id: source.id,
      artifact_id: skill.id,
      url: source.canonical_url,
      section: "When to use",
    },
  ],
  created_at: "2026-08-12T00:00:00Z",
};

const secondSource = {
  ...source,
  id: 8,
  canonical_url: "https://github.com/example/second",
  title: "Second Source",
  source_markdown: "# Second source\n\nNewest selection",
};

const secondTranslation = {
  ...translation,
  id: 23,
  source_id: secondSource.id,
  title: "Second Source（中文）",
  markdown: "# 第二份来源\n\nB 的当前内容。",
};

function deferred<T>() {
  let resolve: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve: resolve! };
}

function configureSourceDetail(artifacts = [translation, skill]) {
  mockedGetSource.mockResolvedValue({ source, artifacts });
}

async function renderAuthenticatedApp() {
  render(<App />);
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("three-pane studio", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    compactViewport = false;
    mediaQueryListeners.clear();
    installMatchMedia();
    mockedGetCurrentSession.mockResolvedValue(defaultSession);
    mockedListSources.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    mockedGetSettings.mockResolvedValue(defaultSettings);
    mockedUpdateSettings.mockImplementation(async (presentation) => ({
      aiConfigured: false,
      presentation,
    }));
    configureSourceDetail();
  });

  it("imports a GitHub URL, selects its saved source, switches artifacts, and saves an edit", async () => {
    mockedImportSource.mockResolvedValue(source);
    mockedEditArtifact.mockResolvedValue({
      ...translation,
      id: 31,
      kind: "user_edit",
      parent_artifact_id: translation.id,
      markdown: "# 中文翻译\n\n已编辑的知识。",
    });

    await renderAuthenticatedApp();

    fireEvent.change(screen.getByLabelText("导入来源链接"), {
      target: { value: source.canonical_url },
    });
    fireEvent.click(screen.getByRole("button", { name: "导入" }));

    expect(await screen.findByText(source.title)).toBeVisible();
    await waitFor(() => expect(mockedGetSource).toHaveBeenCalledWith(source.id, expect.any(AbortSignal)));

    fireEvent.click(screen.getByRole("tab", { name: "中文翻译" }));
    await waitFor(() => expect(screen.getByRole("tab", { name: "中文翻译" })).toHaveAttribute("aria-selected", "true"));
    expect(screen.getByLabelText("Markdown 内容")).toHaveValue(translation.markdown);
    expect(screen.getByRole("heading", { name: "中文翻译" })).toBeVisible();

    fireEvent.click(screen.getByRole("tab", { name: "Distilled Skill" }));
    await waitFor(() => expect(screen.getByRole("tab", { name: "Distilled Skill" })).toHaveAttribute("aria-selected", "true"));
    expect(screen.getByLabelText("Markdown 内容")).toHaveValue(skill.markdown);

    fireEvent.click(screen.getByRole("tab", { name: "中文翻译" }));
    await waitFor(() => expect(screen.getByRole("tab", { name: "中文翻译" })).toHaveAttribute("aria-selected", "true"));
    fireEvent.change(screen.getByLabelText("Markdown 内容"), {
      target: { value: "# 中文翻译\n\n已编辑的知识。" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存版本" }));

    await waitFor(() =>
      expect(mockedEditArtifact).toHaveBeenCalledWith(translation.id, {
        markdown: "# 中文翻译\n\n已编辑的知识。",
      }),
    );
    expect(await screen.findByText("已保存为新版本")).toBeVisible();
  });

  it("keeps a usable restriction banner when source access or generation is unavailable", async () => {
    const partialSource = {
      ...source,
      import_status: "partial" as const,
      failure_reason: "transcript_unavailable",
    };
    mockedListSources.mockResolvedValue({
      items: [partialSource],
      total: 1,
      page: 1,
      page_size: 20,
    });
    mockedGetSource.mockResolvedValue({ source: partialSource, artifacts: [] });
    mockedDeriveSource.mockRejectedValue({
      code: "provider_not_configured",
      message: "The requested provider is not configured.",
    });

    await renderAuthenticatedApp();
    fireEvent.click(await screen.findByRole("button", { name: /Reasoning at Scale/ }));
    expect(await screen.findByText(/部分导入/)).toBeVisible();
    await screen.findByRole("heading", { name: "Reasoning at Scale" });

    fireEvent.click(screen.getByRole("tab", { name: "中文翻译" }));
    await waitFor(() => expect(screen.getByRole("tab", { name: "中文翻译" })).toHaveAttribute("aria-selected", "true"));
    fireEvent.click(screen.getByRole("button", { name: "生成中文翻译" }));

    expect(await screen.findByText(/AI 功能尚未配置/)).toBeVisible();
  });

  it("asks the selected source, then renders its cited answer with source and artifact provenance", async () => {
    mockedListSources.mockResolvedValue({ items: [source], total: 1, page: 1, page_size: 20 });
    mockedChatWithSource.mockResolvedValue(citedAnswer);
    await renderAuthenticatedApp();

    fireEvent.click(await screen.findByRole("button", { name: /Reasoning at Scale/ }));
    await screen.findByRole("heading", { name: "Reasoning at Scale" });

    fireEvent.change(screen.getByLabelText("向来源提问"), {
      target: { value: citedAnswer.question },
    });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));

    await waitFor(() => expect(mockedChatWithSource).toHaveBeenCalledWith(
      source.id,
      citedAnswer.question,
      expect.any(AbortSignal),
    ));
    expect(await screen.findByText(citedAnswer.answer_markdown)).toBeVisible();
    expect(screen.getByRole("link", { name: /原始来源：When to use/ })).toHaveAttribute("href", source.canonical_url);
    expect(screen.getByRole("link", { name: /引用版本 #22/ })).toHaveAttribute("href", "/api/artifacts/22/download");
  });

  it("keeps AI chat errors actionable instead of inventing an answer", async () => {
    mockedListSources.mockResolvedValue({ items: [source], total: 1, page: 1, page_size: 20 });
    mockedChatWithSource.mockRejectedValue({
      code: "provider_not_configured",
      message: "The requested provider is not configured.",
    });
    await renderAuthenticatedApp();

    fireEvent.click(await screen.findByRole("button", { name: /Reasoning at Scale/ }));
    await screen.findByRole("heading", { name: "Reasoning at Scale" });
    fireEvent.change(screen.getByLabelText("向来源提问"), { target: { value: "请总结" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("AI 功能尚未配置");
    expect(screen.queryByText(/当问题需要分步验证/)).not.toBeInTheDocument();
  });

  it("exports only the persisted artifact currently selected in the workspace", async () => {
    mockedListSources.mockResolvedValue({ items: [source], total: 1, page: 1, page_size: 20 });
    await renderAuthenticatedApp();

    fireEvent.click(await screen.findByRole("button", { name: /Reasoning at Scale/ }));
    await screen.findByRole("heading", { name: "Reasoning at Scale" });
    expect(screen.queryByRole("link", { name: "下载 Markdown" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "Distilled Skill" }));
    await waitFor(() => expect(screen.getByLabelText("Markdown 内容")).toHaveValue(skill.markdown));
    expect(screen.getByRole("link", { name: "下载 Markdown" })).toHaveAttribute(
      "href",
      "/api/artifacts/22/download",
    );
  });

  it("switches the preview to its mobile frame without hiding the current content", async () => {
    mockedListSources.mockResolvedValue({ items: [source], total: 1, page: 1, page_size: 20 });
    await renderAuthenticatedApp();

    fireEvent.click(await screen.findByRole("button", { name: /Reasoning at Scale/ }));
    await screen.findByRole("heading", { name: "Reasoning at Scale" });
    fireEvent.click(screen.getByRole("button", { name: "手机预览" }));

    await waitFor(() => expect(mockedUpdateSettings).toHaveBeenLastCalledWith(
      { theme: "system", preview_device: "mobile" },
      expect.any(AbortSignal),
    ));
    expect(screen.getByRole("button", { name: "手机预览" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("Markdown 预览")).toHaveClass("is-mobile-device");
    expect(screen.getByText("Original source text")).toBeVisible();
  });

  it("labels collapsed preview controls with the panel they operate", async () => {
    await setCompactViewport(true);
    mockedListSources.mockResolvedValue({ items: [source], total: 1, page: 1, page_size: 20 });
    await renderAuthenticatedApp();
    await screen.findByText("Reasoning at Scale");

    const toolbar = screen.getByRole("group", { name: "移动工作区工具" });
    const previewButton = within(toolbar).getByRole("button", { name: "预览" });
    const chatButton = within(toolbar).getByRole("button", { name: "来源助手" });
    expect(previewButton).toHaveAttribute("aria-controls", "markdown-preview-surface");
    expect(chatButton).toHaveAttribute("aria-controls", "knowledge-chat-surface");

    fireEvent.click(previewButton);
    expect(previewButton).toHaveAttribute("aria-expanded", "true");
    expect(document.getElementById("markdown-preview-surface")).toBeVisible();
  });

  it("keeps only the selected compact workspace surface reachable", async () => {
    await setCompactViewport(true);
    mockedListSources.mockResolvedValue({ items: [source], total: 1, page: 1, page_size: 20 });
    await renderAuthenticatedApp();

    fireEvent.click(screen.getByRole("button", { name: "打开知识库" }));
    fireEvent.click(await screen.findByRole("button", { name: /Reasoning at Scale/ }));
    await screen.findByRole("heading", { name: "Reasoning at Scale" });

    const previewPanel = screen.getByLabelText("Markdown 预览");
    const toolbar = within(previewPanel).getByRole("group", { name: "移动工作区工具" });
    const previewButton = within(toolbar).getByRole("button", { name: "预览" });
    const chatButton = within(toolbar).getByRole("button", { name: "来源助手" });
    const previewSurface = document.getElementById("markdown-preview-surface")!;
    const chatSurface = document.getElementById("knowledge-chat-surface")!;

    expect(toolbar).toBeVisible();
    expect(screen.getByRole("heading", { name: "Reasoning at Scale" })).toBeVisible();
    expect(previewButton).toHaveAttribute("aria-expanded", "false");
    expect(chatButton).toHaveAttribute("aria-expanded", "false");
    expect(previewSurface).toHaveAttribute("aria-hidden", "true");
    expect(previewSurface).toHaveAttribute("inert");
    expect(chatSurface).toHaveAttribute("aria-hidden", "true");
    expect(chatSurface).toHaveAttribute("inert");

    fireEvent.click(previewButton);

    expect(previewButton).toHaveAttribute("aria-expanded", "true");
    expect(chatButton).toHaveAttribute("aria-expanded", "false");
    expect(previewSurface).not.toHaveAttribute("aria-hidden");
    expect(previewSurface).not.toHaveAttribute("inert");
    expect(chatSurface).toHaveAttribute("aria-hidden", "true");
    expect(chatSurface).toHaveAttribute("inert");
    expect(within(previewPanel).getByRole("heading", { name: "预览" })).toBeVisible();
    expect(within(previewSurface).getByText("Original source text")).toBeVisible();

    fireEvent.click(chatButton);

    expect(toolbar).toBeVisible();
    expect(previewButton).toHaveAttribute("aria-expanded", "false");
    expect(chatButton).toHaveAttribute("aria-expanded", "true");
    expect(previewSurface).toHaveAttribute("aria-hidden", "true");
    expect(previewSurface).toHaveAttribute("inert");
    expect(chatSurface).not.toHaveAttribute("aria-hidden");
    expect(chatSurface).not.toHaveAttribute("inert");
    expect(within(chatSurface).getByRole("textbox", { name: "向来源提问" })).toBeEnabled();
  });

  it("mounts compact preview controls outside the clipped studio shell", async () => {
    await setCompactViewport(true);
    mockedListSources.mockResolvedValue({ items: [source], total: 1, page: 1, page_size: 20 });
    await renderAuthenticatedApp();
    await screen.findByText("Reasoning at Scale");

    const previewPanel = screen.getByLabelText("Markdown 预览");
    expect(previewPanel.parentElement).toBe(document.body);
  });

  it("supports arrow-key movement between artifact tabs", async () => {
    mockedListSources.mockResolvedValue({ items: [source], total: 1, page: 1, page_size: 20 });
    await renderAuthenticatedApp();

    fireEvent.click(await screen.findByRole("button", { name: /Reasoning at Scale/ }));
    await screen.findByRole("heading", { name: "Reasoning at Scale" });

    const originalTab = screen.getByRole("tab", { name: "原文" });
    originalTab.focus();
    fireEvent.keyDown(originalTab, { key: "ArrowRight" });

    expect(screen.getByRole("tab", { name: "中文翻译" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "中文翻译" })).toHaveFocus();
  });

  it("keeps the newest source detail when a slower earlier selection resolves last", async () => {
    const firstDetail = deferred<{ source: typeof source; artifacts: [] }>();
    const secondDetail = deferred<{ source: typeof secondSource; artifacts: [] }>();
    mockedListSources.mockResolvedValue({
      items: [source, secondSource],
      total: 2,
      page: 1,
      page_size: 20,
    });
    mockedGetSource.mockImplementation((sourceId) =>
      sourceId === source.id ? firstDetail.promise : secondDetail.promise,
    );

    await renderAuthenticatedApp();
    fireEvent.click(await screen.findByRole("button", { name: /Reasoning at Scale/ }));
    fireEvent.click(screen.getByRole("button", { name: /Second Source/ }));

    secondDetail.resolve({ source: secondSource, artifacts: [] });
    expect(await screen.findByRole("heading", { name: "Second Source" })).toBeVisible();

    firstDetail.resolve({ source, artifacts: [] });
    await waitFor(() => expect(screen.getByRole("heading", { name: "Second Source" })).toBeVisible());
    expect(screen.queryByRole("heading", { name: "Reasoning at Scale" })).not.toBeInTheDocument();
    expect(mockedGetSource.mock.calls[0]?.[1]).toBeInstanceOf(AbortSignal);
    expect(mockedGetSource.mock.calls[0]?.[1]?.aborted).toBe(true);
  });

  it("does not refresh an older source after its derivation completes while B is selected", async () => {
    const firstDerivation = deferred<typeof translation>();
    const secondDerivation = deferred<typeof secondTranslation>();
    mockedListSources.mockResolvedValue({
      items: [source, secondSource],
      total: 2,
      page: 1,
      page_size: 20,
    });
    mockedGetSource.mockImplementation((sourceId) => Promise.resolve(
      sourceId === source.id
        ? { source, artifacts: [] }
        : { source: secondSource, artifacts: [] },
    ));
    mockedDeriveSource
      .mockImplementationOnce(() => firstDerivation.promise)
      .mockImplementationOnce(() => secondDerivation.promise);

    await renderAuthenticatedApp();
    const firstSourceButton = await screen.findByRole("button", { name: /Reasoning at Scale/ });
    await act(async () => {
      fireEvent.click(firstSourceButton);
      await Promise.resolve();
    });
    await screen.findByRole("heading", { name: "Reasoning at Scale" });
    fireEvent.click(screen.getByRole("tab", { name: "中文翻译" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "生成中文翻译" }));
      await Promise.resolve();
    });
    expect(mockedDeriveSource).toHaveBeenCalledWith(source.id, "translation");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Second Source/ }));
      await Promise.resolve();
    });
    expect(await screen.findByRole("heading", { name: "Second Source" })).toBeVisible();
    await waitFor(() => expect(screen.getByLabelText("Markdown 内容")).toHaveValue(secondSource.source_markdown));
    await act(async () => {
      firstDerivation.resolve(translation);
      await firstDerivation.promise;
      await Promise.resolve();
    });

    await waitFor(() => expect(screen.getByRole("heading", { name: "Second Source" })).toBeVisible());
    expect(screen.getByLabelText("Markdown 内容")).toHaveValue(secondSource.source_markdown);
    expect(mockedGetSource.mock.calls.filter(([sourceId]) => sourceId === source.id)).toHaveLength(1);

    fireEvent.click(screen.getByRole("tab", { name: "中文翻译" }));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "生成中文翻译" }));
      await Promise.resolve();
    });
    expect(mockedDeriveSource).toHaveBeenLastCalledWith(secondSource.id, "translation");
    await act(async () => {
      secondDerivation.resolve(secondTranslation);
      await secondDerivation.promise;
    });
    expect(await screen.findByText("已生成新的知识版本")).toBeVisible();
  });

  it("does not overwrite B's editor or save target when an older A save completes", async () => {
    const firstSave = deferred<Artifact>();
    mockedListSources.mockResolvedValue({
      items: [source, secondSource],
      total: 2,
      page: 1,
      page_size: 20,
    });
    mockedGetSource.mockImplementation((sourceId) => Promise.resolve(
      sourceId === source.id
        ? { source, artifacts: [translation] }
        : { source: secondSource, artifacts: [secondTranslation] },
    ));
    mockedEditArtifact
      .mockImplementationOnce(() => firstSave.promise)
      .mockResolvedValueOnce({
        ...secondTranslation,
        id: 24,
        kind: "user_edit",
        parent_artifact_id: secondTranslation.id,
      });

    await renderAuthenticatedApp();
    const firstSourceButton = await screen.findByRole("button", { name: /Reasoning at Scale/ });
    await act(async () => {
      fireEvent.click(firstSourceButton);
      await Promise.resolve();
    });
    await screen.findByRole("heading", { name: "Reasoning at Scale" });
    fireEvent.click(screen.getByRole("tab", { name: "中文翻译" }));
    await waitFor(() => expect(screen.getByLabelText("Markdown 内容")).toHaveValue(translation.markdown));
    fireEvent.change(screen.getByLabelText("Markdown 内容"), { target: { value: "# A edited" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "保存版本" }));
      await Promise.resolve();
    });
    expect(mockedEditArtifact).toHaveBeenCalledWith(translation.id, { markdown: "# A edited" });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Second Source/ }));
      await Promise.resolve();
    });
    expect(await screen.findByRole("heading", { name: "Second Source" })).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "中文翻译" }));
    await waitFor(() => expect(screen.getByLabelText("Markdown 内容")).toHaveValue(secondTranslation.markdown));
    await act(async () => {
      firstSave.resolve({
        ...translation,
        id: 31,
        kind: "user_edit",
        parent_artifact_id: translation.id,
        markdown: "# A edited",
      });
      await firstSave.promise;
      await Promise.resolve();
    });

    await waitFor(() => expect(screen.getByRole("heading", { name: "Second Source" })).toBeVisible());
    expect(screen.getByLabelText("Markdown 内容")).toHaveValue(secondTranslation.markdown);
    fireEvent.change(screen.getByLabelText("Markdown 内容"), { target: { value: "# B edited" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "保存版本" }));
      await Promise.resolve();
    });
    expect(mockedEditArtifact).toHaveBeenLastCalledWith(secondTranslation.id, { markdown: "# B edited" });
    expect(await screen.findByText("已保存为新版本")).toBeVisible();
  });

  it("traps dialog focus, closes with Escape or its close control, and restores the trigger", async () => {
    await renderAuthenticatedApp();
    const trigger = screen.getByRole("button", { name: "导入新来源" });
    fireEvent.click(trigger);

    const input = await screen.findByLabelText("来源链接");
    expect(input).toHaveFocus();
    const close = screen.getByRole("button", { name: "关闭导入对话框" });
    const cancel = screen.getByRole("button", { name: "取消" });
    close.focus();
    fireEvent.keyDown(close, { key: "Tab", shiftKey: true });
    expect(cancel).toHaveFocus();

    cancel.focus();
    fireEvent.keyDown(cancel, { key: "Tab" });
    expect(screen.getByRole("button", { name: "关闭导入对话框" })).toHaveFocus();

    input.focus();
    fireEvent.keyDown(input, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();

    fireEvent.click(trigger);
    fireEvent.click(await screen.findByRole("button", { name: "关闭导入对话框" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });

  it("keeps native dialog form submission available while focus handling is active", async () => {
    mockedImportSource.mockResolvedValue(source);
    await renderAuthenticatedApp();
    fireEvent.click(screen.getByRole("button", { name: "导入新来源" }));

    fireEvent.change(await screen.findByLabelText("来源链接"), {
      target: { value: source.canonical_url },
    });
    fireEvent.submit(screen.getByRole("dialog").querySelector("form")!);

    await waitFor(() => expect(mockedImportSource).toHaveBeenCalledWith(source.canonical_url));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "导入新来源" })).toHaveFocus();
  });

  it("removes a closed compact library from the accessibility tree and restores focus on close", async () => {
    await setCompactViewport(true);
    await renderAuthenticatedApp();

    const menuTrigger = screen.getByRole("button", { name: "打开知识库" });
    const sidebar = document.querySelector(".knowledge-sidebar");
    expect(sidebar).toHaveAttribute("aria-hidden", "true");
    expect(sidebar).toHaveAttribute("inert");
    expect(screen.queryByRole("heading", { name: "知识库" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "导入新来源" })).not.toBeInTheDocument();

    fireEvent.click(menuTrigger);
    const search = await screen.findByRole("searchbox");
    expect(search).toHaveFocus();
    expect(screen.getByRole("button", { name: "导入新来源" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "关闭知识库" }));
    expect(menuTrigger).toHaveFocus();
    await waitFor(() => expect(screen.queryByRole("heading", { name: "知识库" })).not.toBeInTheDocument());
  });

  it("moves focus out of the library when a viewport change closes it", async () => {
    await renderAuthenticatedApp();

    const search = screen.getByRole("searchbox");
    const menuTrigger = screen.getByRole("button", { name: "打开知识库" });
    search.focus();
    expect(search).toHaveFocus();

    await setCompactViewport(true);

    await waitFor(() => expect(menuTrigger).toHaveFocus());
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(document.querySelector(".knowledge-sidebar")).toHaveAttribute("inert");
  });
});
