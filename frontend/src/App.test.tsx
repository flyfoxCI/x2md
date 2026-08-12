import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { getSettings, listSources, updateSettings } from "./api";
import type { Settings } from "./types";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  listSources: vi.fn(),
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
}));

const mockedListSources = vi.mocked(listSources);
const mockedGetSettings = vi.mocked(getSettings);
const mockedUpdateSettings = vi.mocked(updateSettings);

const defaultSettings: Settings = {
  aiConfigured: false,
  presentation: { theme: "system" as const, preview_device: "desktop" as const },
};

function deferred<T>() {
  let resolve: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve: resolve! };
}

describe("App", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedGetSettings.mockResolvedValue(defaultSettings);
    mockedUpdateSettings.mockImplementation(async (presentation) => ({
      aiConfigured: false,
      presentation,
    }));
    delete document.documentElement.dataset.theme;
  });

  it("loads and renders the knowledge-library source title", async () => {
    mockedListSources.mockResolvedValue({
      items: [
        {
          id: 7,
          canonical_url: "https://github.com/example/reasoning",
          platform: "github",
          title: "Reasoning at Scale",
          author: "Ada Lovelace",
          published_at: null,
          raw_text: "Source material",
          source_markdown: "# Source material",
          metadata_json: {},
          import_status: "ready",
          failure_reason: null,
          created_at: "2026-08-12T00:00:00Z",
          updated_at: "2026-08-12T00:00:00Z",
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });

    render(<App />);

    expect(await screen.findByText("Reasoning at Scale")).toBeVisible();
    expect(mockedListSources).toHaveBeenCalledWith({}, expect.any(AbortSignal));
  });

  it("explains when an AI provider has not been configured", async () => {
    mockedListSources.mockRejectedValue({
      code: "provider_not_configured",
      message: "The AI provider is not configured.",
    });

    render(<App />);

    expect(await screen.findByText(/AI 功能尚未配置/)).toBeVisible();
  });

  it("cancels the library request when the root unmounts without setting an error", async () => {
    let suppliedSignal: AbortSignal | undefined;
    mockedListSources.mockImplementation((_query, signal) => {
      suppliedSignal = signal;
      return new Promise(() => undefined);
    });

    const { unmount } = render(<App />);
    unmount();

    await waitFor(() => expect(suppliedSignal?.aborted).toBe(true));
  });

  it("does not surface an error when the aborted request rejects", async () => {
    mockedListSources.mockImplementation((_query, signal) =>
      new Promise((_, reject) => {
        signal?.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted.", "AbortError"));
        });
      }),
    );

    const { unmount } = render(<App />);
    unmount();

    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });

  it("renders an invalid response as a recoverable library error", async () => {
    mockedListSources.mockRejectedValue({
      code: "invalid_response",
      message: "服务返回的数据格式无效，请稍后重试。",
      status: 200,
    });

    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent("数据格式无效");
  });

  it("hydrates non-secret presentation settings and persists theme and preview device selections", async () => {
    mockedGetSettings.mockResolvedValue({
      aiConfigured: false,
      presentation: { theme: "dark", preview_device: "mobile" },
    });
    render(<App />);

    await waitFor(() => expect(document.documentElement).toHaveAttribute("data-theme", "dark"));
    expect(screen.getByLabelText("界面主题")).toHaveValue("dark");
    expect(screen.getByRole("button", { name: "手机预览" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.change(screen.getByLabelText("界面主题"), { target: { value: "light" } });

    await waitFor(() => expect(mockedUpdateSettings).toHaveBeenCalledWith(
      { theme: "light", preview_device: "mobile" },
      expect.any(AbortSignal),
    ));
    expect(document.documentElement).toHaveAttribute("data-theme", "light");

    fireEvent.click(screen.getByRole("button", { name: "桌面预览" }));
    await waitFor(() => expect(mockedUpdateSettings).toHaveBeenLastCalledWith(
      { theme: "light", preview_device: "desktop" },
      expect.any(AbortSignal),
    ));
    expect(screen.getByRole("button", { name: "桌面预览" })).toHaveAttribute("aria-pressed", "true");
  });

  it("serializes rapid presentation changes and only applies the newest save response", async () => {
    const firstSave = deferred<Settings>();
    const secondSave = deferred<Settings>();
    mockedUpdateSettings
      .mockReturnValueOnce(firstSave.promise)
      .mockReturnValueOnce(secondSave.promise);
    render(<App />);

    fireEvent.click(screen.getByRole("button", { name: "手机预览" }));
    await waitFor(() => expect(mockedUpdateSettings).toHaveBeenCalledWith(
      { theme: "system", preview_device: "mobile" },
      expect.any(AbortSignal),
    ));
    fireEvent.change(screen.getByLabelText("界面主题"), { target: { value: "light" } });

    expect(mockedUpdateSettings).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText("界面主题")).toHaveValue("light");
    expect(screen.getByRole("button", { name: "手机预览" })).toHaveAttribute("aria-pressed", "true");

    await act(async () => {
      firstSave.resolve({
        aiConfigured: false,
        presentation: { theme: "system", preview_device: "desktop" },
      });
      await firstSave.promise;
    });

    await waitFor(() => expect(mockedUpdateSettings).toHaveBeenLastCalledWith(
      { theme: "light", preview_device: "mobile" },
      expect.any(AbortSignal),
    ));
    expect(mockedUpdateSettings).toHaveBeenCalledTimes(2);
    expect(screen.getByLabelText("界面主题")).toHaveValue("light");
    expect(screen.getByRole("button", { name: "手机预览" })).toHaveAttribute("aria-pressed", "true");

    await act(async () => {
      secondSave.resolve({
        aiConfigured: false,
        presentation: { theme: "light", preview_device: "mobile" },
      });
      await secondSave.promise;
    });
    expect(screen.getByLabelText("界面主题")).toHaveValue("light");
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
  });

  it("retries a transient failure for only the latest presentation choice", async () => {
    vi.useFakeTimers();
    try {
      const firstSave = deferred<Settings>();
      mockedUpdateSettings
        .mockReturnValueOnce(firstSave.promise)
        .mockRejectedValueOnce({ code: "network_error", message: "temporary failure" })
        .mockImplementation(async (presentation) => ({ aiConfigured: false, presentation }));
      render(<App />);

      fireEvent.click(screen.getByRole("button", { name: "手机预览" }));
      expect(mockedUpdateSettings).toHaveBeenCalledTimes(1);
      fireEvent.change(screen.getByLabelText("界面主题"), { target: { value: "light" } });

      await act(async () => {
        firstSave.resolve({
          aiConfigured: false,
          presentation: { theme: "system", preview_device: "desktop" },
        });
        await firstSave.promise;
      });

      expect(mockedUpdateSettings).toHaveBeenLastCalledWith(
        { theme: "light", preview_device: "mobile" },
        expect.any(AbortSignal),
      );
      expect(screen.getByLabelText("界面主题")).toHaveValue("light");
      expect(screen.getByRole("button", { name: "手机预览" })).toHaveAttribute("aria-pressed", "true");

      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByRole("status")).toHaveTextContent("正在重试");

      await act(async () => {
        await vi.advanceTimersByTimeAsync(500);
      });

      expect(mockedUpdateSettings).toHaveBeenCalledTimes(3);
      expect(mockedUpdateSettings).toHaveBeenLastCalledWith(
        { theme: "light", preview_device: "mobile" },
        expect.any(AbortSignal),
      );
      expect(screen.getByLabelText("界面主题")).toHaveValue("light");
      expect(screen.getByRole("button", { name: "手机预览" })).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("status")).toHaveTextContent("已保存");

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
      });
      expect(mockedUpdateSettings).toHaveBeenCalledTimes(3);
    } finally {
      vi.clearAllTimers();
      vi.useRealTimers();
    }
  });

  it("does not run a scheduled presentation retry after unmount", async () => {
    vi.useFakeTimers();
    try {
      mockedUpdateSettings.mockRejectedValueOnce({ code: "network_error", message: "temporary failure" });
      const { unmount } = render(<App />);

      fireEvent.click(screen.getByRole("button", { name: "手机预览" }));
      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByRole("status")).toHaveTextContent("正在重试");

      unmount();
      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
      });
      expect(mockedUpdateSettings).toHaveBeenCalledTimes(1);
    } finally {
      vi.clearAllTimers();
      vi.useRealTimers();
    }
  });

  it("sets the persisted system choice on the document for media-scoped theme tokens", async () => {
    render(<App />);

    await waitFor(() => expect(document.documentElement).toHaveAttribute("data-theme", "system"));
    expect(screen.getByLabelText("界面主题")).toHaveValue("system");
  });

  it("keeps a local choice over a late read and gives an actionable message after bounded failures", async () => {
    vi.useFakeTimers();
    try {
      const initialSettings = deferred<typeof defaultSettings>();
      mockedGetSettings.mockReturnValue(initialSettings.promise);
      mockedUpdateSettings.mockRejectedValue({ code: "network_error", message: "do not expose internals" });
      render(<App />);

      fireEvent.change(screen.getByLabelText("界面主题"), { target: { value: "light" } });
      await act(async () => {
        initialSettings.resolve({
          aiConfigured: false,
          presentation: { theme: "dark", preview_device: "mobile" },
        });
        await initialSettings.promise;
      });

      expect(document.documentElement).toHaveAttribute("data-theme", "light");
      expect(screen.getByLabelText("界面主题")).toHaveValue("light");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1_000);
      });

      expect(mockedUpdateSettings).toHaveBeenCalledTimes(3);
      expect(screen.getByLabelText("界面主题")).toHaveValue("light");
      expect(screen.getByRole("status")).toHaveTextContent("显示设置仍未保存。请再次选择所需显示设置以重试。");

      await act(async () => {
        await vi.advanceTimersByTimeAsync(10_000);
      });
      expect(mockedUpdateSettings).toHaveBeenCalledTimes(3);
    } finally {
      vi.clearAllTimers();
      vi.useRealTimers();
    }
  });

  it("aborts the initial presentation-settings request on unmount", async () => {
    let suppliedSignal: AbortSignal | undefined;
    mockedGetSettings.mockImplementation((signal) => {
      suppliedSignal = signal;
      return new Promise(() => undefined);
    });

    const { unmount } = render(<App />);
    unmount();

    await waitFor(() => expect(suppliedSignal?.aborted).toBe(true));
  });
});
