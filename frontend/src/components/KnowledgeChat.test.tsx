import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { chatWithSource } from "../api";
import { KnowledgeChat } from "./KnowledgeChat";

vi.mock("../api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api")>()),
  chatWithSource: vi.fn(),
}));

const mockedChatWithSource = vi.mocked(chatWithSource);

const source = {
  id: 7,
  canonical_url: "https://example.com/source",
  platform: "web",
  title: "Selected source",
  author: null,
  published_at: null,
  raw_text: "source material",
  source_markdown: "# source material",
  metadata_json: {},
  import_status: "ready" as const,
  failure_reason: null,
  created_at: "2026-08-12T00:00:00Z",
  updated_at: "2026-08-12T00:00:00Z",
};

function deferred<T>() {
  let resolve: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve: resolve! };
}

describe("KnowledgeChat", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it.each([
    ["provider_not_configured", "AI 功能尚未配置"],
    ["source_unavailable", "当前来源没有足够的可用材料"],
    ["provider_error", "AI 服务暂时未能完成回答"],
  ])("shows %s as an actionable error without an invented answer", async (code, expectedCopy) => {
    mockedChatWithSource.mockRejectedValue({ code, message: "backend message" });
    render(<KnowledgeChat source={source} />);

    fireEvent.change(screen.getByLabelText("向来源提问"), { target: { value: "问一个问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(expectedCopy);
    expect(screen.queryByText("backend message")).not.toBeInTheDocument();
  });

  it("aborts an in-flight source-scoped chat request when the selected source changes", async () => {
    const pending = deferred<never>();
    mockedChatWithSource.mockReturnValue(pending.promise);
    const { rerender } = render(<KnowledgeChat source={source} />);

    fireEvent.change(screen.getByLabelText("向来源提问"), { target: { value: "问一个问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    await waitFor(() => expect(mockedChatWithSource).toHaveBeenCalledTimes(1));

    rerender(<KnowledgeChat source={{ ...source, id: 8, title: "New source" }} />);

    expect(mockedChatWithSource.mock.calls[0]?.[2]?.aborted).toBe(true);
    expect(screen.getByLabelText("向来源提问")).toHaveValue("");
  });

  it("uses the shared safe Markdown boundary for an AI answer", async () => {
    mockedChatWithSource.mockResolvedValue({
      id: 9,
      source_id: source.id,
      question: "Can I trust this?",
      answer_markdown: "![Tracker](https://tracker.example/pixel.png)\n\n[Unsafe](javascript:alert(1))\n\n[Safe](https://example.com/source)",
      citations_json: [],
      created_at: "2026-08-12T00:00:00Z",
    });
    render(<KnowledgeChat source={source} />);

    fireEvent.change(screen.getByLabelText("向来源提问"), { target: { value: "Can I trust this?" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));

    expect(await screen.findByRole("link", { name: "Safe" })).toHaveAttribute("href", "https://example.com/source");
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText("Unsafe").closest("a")).toBeNull();
  });

  it("renders citation anchors only for absolute HTTPS URLs", async () => {
    mockedChatWithSource.mockResolvedValue({
      id: 10,
      source_id: source.id,
      question: "Which citations are safe?",
      answer_markdown: "Only verified citations are linked.",
      citations_json: [
        { source_id: source.id, artifact_id: null, url: "javascript:alert(1)", section: "JavaScript citation" },
        { source_id: source.id, artifact_id: null, url: "data:text/html,unsafe", section: "Data citation" },
        { source_id: source.id, artifact_id: null, url: "/relative-citation", section: "Relative citation" },
        {
          source_id: source.id,
          artifact_id: null,
          url: "https://example.com/citation?section=verified",
          section: "HTTPS citation",
        },
      ],
      created_at: "2026-08-12T00:00:00Z",
    });
    render(<KnowledgeChat source={source} />);

    fireEvent.change(screen.getByLabelText("向来源提问"), { target: { value: "Which citations are safe?" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));

    const citations = await screen.findByRole("list", { name: "回答引用" });
    const verifiedCitation = within(citations).getByRole("link", { name: "原始来源：HTTPS citation" });
    expect(verifiedCitation).toHaveAttribute("href", "https://example.com/citation?section=verified");
    expect(verifiedCitation).toHaveAttribute("rel", "noopener noreferrer");
    expect(verifiedCitation).toHaveAttribute("target", "_blank");
    expect(screen.getByText("原始来源：JavaScript citation").closest("a")).toBeNull();
    expect(screen.getByText("原始来源：Data citation").closest("a")).toBeNull();
    expect(screen.getByText("原始来源：Relative citation").closest("a")).toBeNull();
  });
});
