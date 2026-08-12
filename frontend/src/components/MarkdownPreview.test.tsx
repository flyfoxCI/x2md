import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarkdownPreview } from "./MarkdownPreview";

describe("MarkdownPreview", () => {
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
});
