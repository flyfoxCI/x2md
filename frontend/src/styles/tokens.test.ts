import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const tokensPath = resolve(process.cwd(), "src/styles/tokens.css");
const workspacePath = resolve(process.cwd(), "src/styles/workspace.css");
const appPath = resolve(process.cwd(), "src/styles/app.css");

function hexToRgb(value: string) {
  const normalized = value.replace("#", "");
  return [0, 2, 4].map((offset) => Number.parseInt(normalized.slice(offset, offset + 2), 16) / 255);
}

function luminance(value: string) {
  return hexToRgb(value).map((channel) => (
    channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
  )).reduce((sum, channel, index) => sum + channel * [0.2126, 0.7152, 0.0722][index], 0);
}

function contrast(foreground: string, background: string) {
  const [lighter, darker] = [luminance(foreground), luminance(background)].sort((left, right) => right - left);
  return (lighter + 0.05) / (darker + 0.05);
}

describe("presentation theme tokens", () => {
  it("applies the dark token set to the system theme only when the OS prefers dark", async () => {
    const css = await readFile(tokensPath, "utf8");

    expect(css).toMatch(/:root\[data-theme="dark"\]\s*\{[\s\S]*--paper:\s*#132228/);
    expect(css).toMatch(
      /@media\s*\(prefers-color-scheme:\s*dark\)\s*\{[\s\S]*:root\[data-theme="system"\]\s*\{[\s\S]*--paper:\s*#132228[\s\S]*:root\[data-theme="system"\]\s+\.mobile-workspace-tools/,
    );
    expect(css).not.toMatch(/:root\[data-theme="light"\][\s\S]*--paper:\s*#132228/);
    expect(css).not.toMatch(
      /:root\[data-theme="dark"\]\s+\.mobile-workspace-tools,\s*:root\[data-theme="system"\]\s+\.mobile-workspace-tools/,
    );
  });

  it("uses semantic high-contrast control and preview colors in dark mode", async () => {
    const [tokensCss, workspaceCss] = await Promise.all([
      readFile(tokensPath, "utf8"),
      readFile(workspacePath, "utf8"),
    ]);
    const darkTokens = tokensCss.match(/:root\[data-theme="dark"\]\s*\{([\s\S]*?)\n\}/)?.[1] ?? "";
    const token = (name: string) => darkTokens.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`))?.[1] ?? "";

    expect(contrast(token("--control-ink"), token("--control-surface"))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token("--control-active-ink"), token("--control-active-surface"))).toBeGreaterThanOrEqual(4.5);
    expect(workspaceCss).toMatch(/\.artifact-tabs button\s*\{[^}]*color:\s*var\(--control-ink\)/);
    expect(workspaceCss).toMatch(/\.preview-heading h2\s*\{[^}]*color:\s*var\(--ink\)/);
    expect(workspaceCss).toMatch(/\.preview-device-toggle button\s*\{[^}]*color:\s*var\(--control-ink\)/);
  });

  it("keeps dark status, link, and mobile preview-frame text on semantic contrast-safe surfaces", async () => {
    const [tokensCss, workspaceCss, appCss] = await Promise.all([
      readFile(tokensPath, "utf8"),
      readFile(workspacePath, "utf8"),
      readFile(appPath, "utf8"),
    ]);
    const darkTokens = tokensCss.match(/:root\[data-theme="dark"\]\s*\{([\s\S]*?)\n\}/)?.[1] ?? "";
    const token = (name: string) => darkTokens.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`))?.[1] ?? "";

    expect(contrast(token("--link"), token("--paper"))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token("--success-ink"), token("--success-bg"))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token("--preview-frame-ink"), token("--preview-frame-surface"))).toBeGreaterThanOrEqual(4.5);
    expect(workspaceCss).toMatch(/\.source-provenance a,\s*\.download-link,\s*\.markdown-preview a,\s*\.chat-citations a\s*\{[^}]*color:\s*var\(--link\)/);
    expect(workspaceCss).toMatch(/\.preview-panel\.is-mobile-device\s+\.markdown-preview\s*\{[^}]*color:\s*var\(--preview-frame-ink\);[^}]*background:\s*var\(--preview-frame-surface\)/);
    expect(appCss).toMatch(/\.header-status\s*\{[^}]*color:\s*var\(--muted\)/);
    expect(appCss).toMatch(/\.status-message\.is-success\s*\{[^}]*color:\s*var\(--success-ink\)/);
  });
});
