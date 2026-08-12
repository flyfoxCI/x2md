import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { listSources } from "./api";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  listSources: vi.fn(),
}));

const mockedListSources = vi.mocked(listSources);

describe("App", () => {
  beforeEach(() => {
    mockedListSources.mockReset();
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
});
