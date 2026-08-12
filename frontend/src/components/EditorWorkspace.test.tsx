import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "../App";
import {
  deriveSource,
  editArtifact,
  getSource,
  importSource,
  listSources,
} from "../api";
import type { Artifact } from "../types";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  listSources: vi.fn(),
  importSource: vi.fn(),
  getSource: vi.fn(),
  deriveSource: vi.fn(),
  editArtifact: vi.fn(),
}));

const mockedListSources = vi.mocked(listSources);
const mockedImportSource = vi.mocked(importSource);
const mockedGetSource = vi.mocked(getSource);
const mockedDeriveSource = vi.mocked(deriveSource);
const mockedEditArtifact = vi.mocked(editArtifact);

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

describe("three-pane studio", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    compactViewport = false;
    mediaQueryListeners.clear();
    installMatchMedia();
    mockedListSources.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
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

    render(<App />);

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

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Reasoning at Scale/ }));
    expect(await screen.findByText(/部分导入/)).toBeVisible();
    await screen.findByRole("heading", { name: "Reasoning at Scale" });

    fireEvent.click(screen.getByRole("tab", { name: "中文翻译" }));
    await waitFor(() => expect(screen.getByRole("tab", { name: "中文翻译" })).toHaveAttribute("aria-selected", "true"));
    fireEvent.click(screen.getByRole("button", { name: "生成中文翻译" }));

    expect(await screen.findByText(/AI 功能尚未配置/)).toBeVisible();
  });

  it("supports arrow-key movement between artifact tabs", async () => {
    mockedListSources.mockResolvedValue({ items: [source], total: 1, page: 1, page_size: 20 });
    render(<App />);

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

    render(<App />);
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

    render(<App />);
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

    render(<App />);
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
    render(<App />);
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
    render(<App />);
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
    render(<App />);

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
    render(<App />);

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
