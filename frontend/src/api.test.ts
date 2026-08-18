import { afterEach, describe, expect, it, vi } from "vitest";

import {
  chatWithSource,
  changePassword,
  clearAuthentication,
  deriveSource,
  editArtifact,
  getCurrentSession,
  getSettings,
  getSource,
  importSource,
  listSources,
  login,
  logout,
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

const authenticatedSession = {
  user: { id: 7, username: "admin" },
  csrfToken: "csrf-token-one",
};

const rotatedSession = {
  user: { id: 7, username: "admin" },
  csrfToken: "csrf-token-two",
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

describe("authentication transport", () => {
  afterEach(() => {
    clearAuthentication();
    vi.unstubAllGlobals();
  });

  it("posts the exact login credentials with same-origin browser credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response(authenticatedSession));
    const storageSpies = [
      vi.spyOn(Storage.prototype, "getItem"),
      vi.spyOn(Storage.prototype, "setItem"),
      vi.spyOn(Storage.prototype, "removeItem"),
      vi.spyOn(Storage.prototype, "clear"),
    ];
    const indexedDb = { open: vi.fn() };
    vi.stubGlobal("indexedDB", indexedDb);
    vi.stubGlobal("fetch", fetchMock);

    await expect(login("admin", "correct horse battery staple")).resolves.toEqual(
      authenticatedSession,
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/login",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        body: JSON.stringify({
          username: "admin",
          password: "correct horse battery staple",
        }),
      }),
    );
    const options = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(options.headers);
    expect(headers.get("Accept")).toBe("application/json");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("X-CSRF-Token")).toBeNull();
    for (const storageSpy of storageSpies) {
      expect(storageSpy).not.toHaveBeenCalled();
    }
    expect(indexedDb.open).not.toHaveBeenCalled();
  });

  it.each([
    ["user", without(authenticatedSession, "user")],
    ["CSRF token", without(authenticatedSession, "csrfToken")],
    ["user id", { ...authenticatedSession, user: without(authenticatedSession.user, "id") }],
    [
      "username",
      { ...authenticatedSession, user: without(authenticatedSession.user, "username") },
    ],
  ])("rejects an auth response missing the required %s", async (_name, payload) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(payload)));

    await expect(login("admin", "password")).rejects.toMatchObject({
      code: "invalid_response",
      status: 200,
    });
  });

  it("does not install a CSRF token from a malformed login response", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(without(authenticatedSession, "csrfToken")))
      .mockResolvedValueOnce(response(source));
    vi.stubGlobal("fetch", fetchMock);

    await expect(login("admin", "password")).rejects.toMatchObject({
      code: "invalid_response",
      status: 200,
    });
    await importSource("https://example.com/article");

    const options = fetchMock.mock.calls[1]?.[1] as RequestInit;
    expect(new Headers(options.headers).get("X-CSRF-Token")).toBeNull();
  });

  it("installs the CSRF token for legacy unsafe requests but omits it from reads", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(authenticatedSession))
      .mockResolvedValueOnce(response(source))
      .mockResolvedValueOnce(response(settings));
    vi.stubGlobal("fetch", fetchMock);

    await login("admin", "password");
    await importSource("https://example.com/article");
    await getSettings();

    const unsafeOptions = fetchMock.mock.calls[1]?.[1] as RequestInit;
    const readOptions = fetchMock.mock.calls[2]?.[1] as RequestInit;
    expect(new Headers(unsafeOptions.headers).get("X-CSRF-Token")).toBe("csrf-token-one");
    expect(new Headers(readOptions.headers).get("X-CSRF-Token")).toBeNull();
    expect(unsafeOptions.credentials).toBe("same-origin");
    expect(readOptions.credentials).toBe("same-origin");
  });

  it("sends the exact password-change body and replaces the CSRF token", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(authenticatedSession))
      .mockResolvedValueOnce(response(rotatedSession))
      .mockResolvedValueOnce(response(source));
    vi.stubGlobal("fetch", fetchMock);

    await login("admin", "old password");
    await expect(
      changePassword("old password", "new secure password"),
    ).resolves.toEqual(rotatedSession);
    await importSource("https://example.com/article");

    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/auth/change-password",
      expect.objectContaining({
        method: "POST",
        credentials: "same-origin",
        body: JSON.stringify({
          currentPassword: "old password",
          newPassword: "new secure password",
        }),
      }),
    );
    const passwordOptions = fetchMock.mock.calls[1]?.[1] as RequestInit;
    const subsequentWriteOptions = fetchMock.mock.calls[2]?.[1] as RequestInit;
    expect(new Headers(passwordOptions.headers).get("X-CSRF-Token")).toBe("csrf-token-one");
    expect(new Headers(subsequentWriteOptions.headers).get("X-CSRF-Token")).toBe(
      "csrf-token-two",
    );
  });

  it("clears a stale CSRF token after a 401 before the next unsafe request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(authenticatedSession))
      .mockResolvedValueOnce(
        response(
          {
            detail: {
              code: "authentication_required",
              message: "Authentication is required.",
            },
          },
          401,
        ),
      )
      .mockResolvedValueOnce(response(settings));
    vi.stubGlobal("fetch", fetchMock);

    await login("admin", "password");
    await expect(importSource("https://example.com/article")).rejects.toMatchObject({
      code: "authentication_required",
      status: 401,
    });
    await updateSettings({ theme: "dark", preview_device: "mobile" });

    const rejectedWriteOptions = fetchMock.mock.calls[1]?.[1] as RequestInit;
    const laterWriteOptions = fetchMock.mock.calls[2]?.[1] as RequestInit;
    expect(new Headers(rejectedWriteOptions.headers).get("X-CSRF-Token")).toBe(
      "csrf-token-one",
    );
    expect(new Headers(laterWriteOptions.headers).get("X-CSRF-Token")).toBeNull();
  });

  it("uses the CSRF token for logout, accepts its empty 204, and clears it", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(authenticatedSession))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(response(source));
    vi.stubGlobal("fetch", fetchMock);

    await login("admin", "password");
    await expect(logout()).resolves.toBeUndefined();
    await importSource("https://example.com/article");

    const logoutOptions = fetchMock.mock.calls[1]?.[1] as RequestInit;
    const laterWriteOptions = fetchMock.mock.calls[2]?.[1] as RequestInit;
    expect(new Headers(logoutOptions.headers).get("X-CSRF-Token")).toBe("csrf-token-one");
    expect(new Headers(laterWriteOptions.headers).get("X-CSRF-Token")).toBeNull();
  });

  it("uses same-origin credentials for every browser API request", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ items: [source], total: 1, page: 1, page_size: 20 }))
      .mockResolvedValueOnce(response(source))
      .mockResolvedValueOnce(response({ source, artifacts: [] }))
      .mockResolvedValueOnce(response(artifact))
      .mockResolvedValueOnce(response(artifact))
      .mockResolvedValueOnce(response(chatTurn))
      .mockResolvedValueOnce(response(settings))
      .mockResolvedValueOnce(response(settings))
      .mockResolvedValueOnce(response(authenticatedSession))
      .mockResolvedValueOnce(response(authenticatedSession))
      .mockResolvedValueOnce(response(rotatedSession))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await listSources();
    await importSource("https://example.com/article");
    await getSource(1);
    await deriveSource(1, "summary");
    await editArtifact(2, { markdown: "# Edit" });
    await chatWithSource(1, "What changed?");
    await getSettings();
    await updateSettings({ theme: "system", preview_device: "desktop" });
    await getCurrentSession();
    await login("admin", "password");
    await changePassword("password", "new secure password");
    await logout();

    expect(fetchMock).toHaveBeenCalledTimes(12);
    for (const call of fetchMock.mock.calls) {
      expect((call[1] as RequestInit).credentials).toBe("same-origin");
    }
  });
});
