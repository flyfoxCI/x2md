import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const workspacePath = resolve(process.cwd(), "src/styles/workspace.css");
const appPath = resolve(process.cwd(), "src/styles/app.css");

describe("compact preview overlay styles", () => {
  it("keeps the collapsed toolbar at the viewport edge without stretching its auto grid row", async () => {
    const css = await readFile(workspacePath, "utf8");

    expect(css).toMatch(/\.preview-panel\s*\{[^}]*height:\s*calc\(3rem\s*\+\s*1px\);[^}]*grid-template-rows:\s*auto;[^}]*align-content:\s*start/);
    expect(css).toMatch(/\.mobile-workspace-tools\s*\{[^}]*min-height:\s*3rem/);
    expect(css).toMatch(/\.preview-panel\[data-mobile-surface="preview"\],\s*\.preview-panel\[data-mobile-surface="chat"\]\s*\{[^}]*top:\s*var\(--app-header-height\)/);
  });

  it("anchors an expanded compact overlay below the responsive header and above the safe-area inset", async () => {
    const [workspaceCss, appCss] = await Promise.all([
      readFile(workspacePath, "utf8"),
      readFile(appPath, "utf8"),
    ]);

    expect(appCss).toMatch(/:root\s*\{[^}]*--app-header-height:\s*70px/);
    expect(appCss).toMatch(/\.studio-shell\s*\{[^}]*grid-template-rows:\s*var\(--app-header-height\)/);
    expect(appCss).toMatch(/@media\s*\(max-width:\s*900px\)\s*\{[\s\S]*:root\s*\{[^}]*--app-header-height:\s*calc\(7rem\s*\+\s*env\(safe-area-inset-top,\s*0px\)\)/);
    expect(workspaceCss).toMatch(/\.preview-panel\[data-mobile-surface="preview"\],\s*\.preview-panel\[data-mobile-surface="chat"\]\s*\{[^}]*top:\s*var\(--app-header-height\);[^}]*height:\s*calc\(100dvh\s*-\s*var\(--app-header-height\)\s*-\s*env\(safe-area-inset-bottom,\s*0px\)\)/);
  });

  it("reserves the compact overlay height for the editor at tablet widths", async () => {
    const css = await readFile(workspacePath, "utf8");

    expect(css).toMatch(/@media\s*\(max-width:\s*1120px\)\s*\{[\s\S]*\.workspace-column\s*\{[^}]*padding-bottom:\s*calc\(3rem\s*\+\s*1px\s*\+\s*env\(safe-area-inset-bottom,\s*0px\)\)/);
    expect(css).toMatch(/@media\s*\(max-width:\s*720px\)\s*\{[\s\S]*\.workspace-column\s*\{[^}]*padding-bottom:\s*calc\(3rem\s*\+\s*1px\s*\+\s*env\(safe-area-inset-bottom,\s*0px\)\)/);
  });
});
