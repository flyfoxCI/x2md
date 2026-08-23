import { afterEach, describe, expect, it, vi } from "vitest";

import {
  chatWithSource,
  deriveSource,
  editArtifact,
  getSettings,
  getResearchRun,
  getSource,
  importSource,
  listSources,
  startResearch,
  updateSettings,
} from "./api";

const source = {
  id: 1,
  canonical_url: "https://example.com/source",
  platform: "web",
  title: "Source",
  author: null,
  published_at: null,
  raw_text: "Raw material",
  source_markdown: "# Raw material",
  metadata_json: { fixture: true },
  import_status: "ready",
  failure_reason: null,
  created_at: "2026-08-12T00:00:00Z",
  updated_at: "2026-08-12T00:00:00Z",
};

const artifact = {
  id: 2,
  source_id: 1,
  kind: "summary",
  title: "Summary",
  markdown: "# Summary",
  language: "zh",
  parent_artifact_id: null,
  model_metadata_json: { model: "fixture" },
  created_at: "2026-08-12T00:00:00Z",
  updated_at: "2026-08-12T00:00:00Z",
};

const chatTurn = {
  id: 3,
  source_id: 1,
  question: "What changed?",
  answer_markdown: "Only this source.",
  citations_json: [
    {
      source_id: 1,
      artifact_id: null,
      url: "https://example.com/source",
      section: "Original source",
    },
  ],
  created_at: "2026-08-12T00:00:00Z",
};

const settings = {
  aiConfigured: false,
  presentation: { theme: "system", preview_device: "desktop" },
};

const researchRun = {
  id: 7,
  source_id: 1,
  trigger: "manual",
  status: "queued",
  phase: null,
  budget_json: {},
  coverage_json: {},
  attempt_count: 0,
  max_attempts: 2,
  next_attempt_at: null,
  failure_code: null,
  provider_metadata_json: {},
  started_at: null,
  finished_at: null,
  created_at: "2026-08-23T00:00:00Z",
  updated_at: "2026-08-23T00:00:00Z",
};

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function without(object: Record<string, unknown>, field: string): Record<string, unknown> {
  const copy = { ...object };
  delete copy[field];
  return copy;
}

describe("listSources", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("normalizes a successful response body read failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        text: vi.fn().mockRejectedValue(new Error("stream failure")),
      }),
    );

    await expect(listSources()).rejects.toMatchObject({
      code: "invalid_response",
      status: 200,
    });
  });

  it("turns a successful non-JSON response into a stable API error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("not JSON", { status: 200 })),
    );

    await expect(listSources()).rejects.toMatchObject({
      code: "invalid_response",
      message: expect.any(String),
      status: 200,
    });
  });

  it("rejects a malformed source page before a component can render it", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ items: "not-an-array", total: 1 }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(listSources()).rejects.toMatchObject({
      code: "invalid_response",
      status: 200,
    });
  });
});

describe("public API response guards", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each([
    ["import", () => importSource("https://example.com/article")],
    ["source detail", () => getSource(1)],
    ["derivation", () => deriveSource(1, "summary")],
    ["artifact edit", () => editArtifact(1, { markdown: "# edit" })],
    ["chat", () => chatWithSource(1, "What changed?")],
    ["settings read", () => getSettings()],
    ["research run", () => getResearchRun(7)],
    ["research start", () => startResearch(1)],
    [
      "settings write",
      () => updateSettings({ theme: "system", preview_device: "desktop" }),
    ],
  ])("rejects a malformed successful %s response", async (_name, call) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ unexpected: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(call()).rejects.toMatchObject({
      code: "invalid_response",
      status: 200,
    });
  });

  it.each([
    ["source", () => importSource("https://example.com/article"), source, Object.keys(source)],
    [
      "source page",
      () => listSources(),
      { items: [source], total: 1, page: 1, page_size: 20 },
      ["items", "total", "page", "page_size"],
    ],
    ["artifact", () => deriveSource(1, "summary"), artifact, Object.keys(artifact)],
    ["chat turn", () => chatWithSource(1, "What changed?"), chatTurn, Object.keys(chatTurn)],
    ["settings", () => getSettings(), settings, ["aiConfigured", "presentation"]],
    ["research run", () => getResearchRun(7), researchRun, Object.keys(researchRun)],
  ])("rejects a %s missing each required key", async (_name, call, payload, fields) => {
    for (const field of fields) {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(without(payload, field))));

      await expect(call()).rejects.toMatchObject({
        code: "invalid_response",
        status: 200,
      });
    }
  });

  it("rejects a chat citation missing a required provenance key", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response({ ...chatTurn, citations_json: [without(chatTurn.citations_json[0], "url")] }),
      ),
    );

    await expect(chatWithSource(1, "What changed?")).rejects.toMatchObject({
      code: "invalid_response",
      status: 200,
    });
  });

  it.each([
    ["non-JSON body", new Response("server outage", { status: 503 })],
    [
      "unreadable body",
      { ok: false, status: 503, text: vi.fn().mockRejectedValue(new Error("stream failure")) },
    ],
  ])("normalizes an HTTP error with a %s as request_failed", async (_name, rawResponse) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(rawResponse));

    await expect(listSources()).rejects.toMatchObject({
      code: "request_failed",
      status: 503,
    });
  });
});
