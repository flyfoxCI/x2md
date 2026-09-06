import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MarkdownPreview } from "./MarkdownPreview";

const initialize = vi.fn();
const renderDiagram = vi.fn();

vi.mock("mermaid", () => ({
  default: {
    initialize,
    render: renderDiagram,
  },
}));

describe("MarkdownPreview", () => {
  beforeEach(() => {
    initialize.mockClear();
    renderDiagram.mockReset();
    renderDiagram.mockResolvedValue({ svg: '<svg aria-label="architecture"></svg>' });
  });

  it("renders Markdown while leaving raw HTML inert", () => {
    render(<MarkdownPreview markdown={"# Safe title\n\n<script>window.alert('unsafe')</script>\n\n[Source](https://example.com)"} />);

    expect(screen.getByRole("heading", { name: "Safe title" })).toBeVisible();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.getByRole("link", { name: "Source" })).toHaveAttribute("href", "https://example.com");
  });

  it("does not render remote images or unsafe link schemes from imported Markdown", () => {
    render(
      <MarkdownPreview
        markdown={"![Tracker](https://tracker.example/pixel.png)\n\n[Unsafe](javascript:alert(1))\n\n[Data](data:text/plain,unsafe)\n\n[Safe](https://example.com/source)"}
      />,
    );

    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText("Unsafe").closest("a")).toBeNull();
    expect(screen.getByText("Data").closest("a")).toBeNull();
    expect(screen.getByRole("link", { name: "Safe" })).toHaveAttribute("href", "https://example.com/source");
  });

  it("renders fenced Mermaid as a strict, accessible research diagram", async () => {
    render(<MarkdownPreview markdown={'## 一图综述\n\n```mermaid\nflowchart LR\nA["输入"] --> B["结果"]\n```'} />);

    expect(await screen.findByLabelText("研究一图综述")).toContainHTML("svg");
    expect(initialize).toHaveBeenCalledWith(expect.objectContaining({
      securityLevel: "strict",
      startOnLoad: false,
      flowchart: expect.objectContaining({ htmlLabels: false }),
    }));
    expect(renderDiagram).toHaveBeenCalledWith(expect.stringMatching(/^research-diagram-/), expect.stringContaining("flowchart LR"));
  });

  it("falls back to readable source when Mermaid cannot render", async () => {
    renderDiagram.mockRejectedValueOnce(new Error("invalid diagram"));
    render(<MarkdownPreview markdown={'```mermaid\nflowchart LR\nA-->\n```'} />);

    expect(await screen.findByRole("note")).toHaveTextContent("图示暂时无法渲染");
    expect(screen.getByText(/flowchart LR/)).toBeVisible();
  });

  it("does not execute unsafe Mermaid directives from legacy or edited Markdown", async () => {
    render(<MarkdownPreview markdown={'```mermaid\nflowchart TB\nclick A "javascript:alert(1)"\n```'} />);

    expect(await screen.findByRole("note")).toHaveTextContent("图示不符合安全规则");
    expect(renderDiagram).not.toHaveBeenCalled();
    expect(document.querySelector("svg")).toBeNull();
  });
});
