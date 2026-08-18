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

const latestSession = {
  user: { id: 7, username: "admin" },
  csrfToken: "csrf-token-three",
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

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolvePromise!: (value: T | PromiseLike<T>) => void;
  const promise = new Promise<T>((resolve) => {
    resolvePromise = resolve;
  });
  return { promise, resolve: (value) => resolvePromise(value) };
}

describe("listSources", () => {
  afterEach(() => {
    vi.restoreAllMocks();
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
    vi.restoreAllMocks();
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
    vi.restoreAllMocks();
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

  it("keeps the current CSRF token after an invalid current password", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(authenticatedSession))
      .mockResolvedValueOnce(
        response(
          {
            detail: {
              code: "invalid_credentials",
              message: "Invalid username or password.",
            },
          },
          401,
        ),
      )
      .mockResolvedValueOnce(response(source));
    vi.stubGlobal("fetch", fetchMock);

    await login("admin", "password");
    await expect(changePassword("incorrect password", "new secure password")).rejects.toMatchObject(
      {
        code: "invalid_credentials",
        status: 401,
      },
    );
    await importSource("https://example.com/article");

    const laterWriteOptions = fetchMock.mock.calls[2]?.[1] as RequestInit;
    expect(new Headers(laterWriteOptions.headers).get("X-CSRF-Token")).toBe(
      "csrf-token-one",
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

  it("clears only a current safe authentication-required response", async () => {
    const cases = [
      {
        name: "safe authentication-required envelope",
        rejectedResponse: response(
          {
            detail: {
              code: "authentication_required",
              message: "Authentication is required.",
            },
          },
          401,
        ),
        expectedToken: null,
      },
      {
        name: "non-JSON 401 response",
        rejectedResponse: new Response("server outage", { status: 401 }),
        expectedToken: "csrf-token-one",
      },
      {
        name: "unreadable 401 response",
        rejectedResponse: {
          ok: false,
          status: 401,
          text: vi.fn().mockRejectedValue(new Error("stream failure")),
        },
        expectedToken: "csrf-token-one",
      },
    ];

    for (const { rejectedResponse, expectedToken } of cases) {
      clearAuthentication();
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(response(authenticatedSession))
        .mockResolvedValueOnce(rejectedResponse)
        .mockResolvedValueOnce(response(source));
      vi.stubGlobal("fetch", fetchMock);

      await login("admin", "password");
      await expect(importSource("https://example.com/article")).rejects.toMatchObject({
        status: 401,
      });
      await importSource("https://example.com/article");

      const laterWriteOptions = fetchMock.mock.calls[2]?.[1] as RequestInit;
      expect(new Headers(laterWriteOptions.headers).get("X-CSRF-Token")).toBe(expectedToken);
    }
  });

  it("does not let an old authentication-required response clear a newer session", async () => {
    const delayedResponse = deferred<Response>();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(authenticatedSession))
      .mockReturnValueOnce(delayedResponse.promise)
      .mockResolvedValueOnce(response(rotatedSession))
      .mockResolvedValueOnce(response(source));
    vi.stubGlobal("fetch", fetchMock);

    await login("admin", "password");
    const staleRequest = importSource("https://example.com/old-request");
    await login("admin", "password");
    delayedResponse.resolve(
      response(
        {
          detail: {
            code: "authentication_required",
            message: "Authentication is required.",
          },
        },
        401,
      ),
    );

    await expect(staleRequest).rejects.toMatchObject({
      code: "authentication_required",
      status: 401,
    });
    await importSource("https://example.com/new-request");

    const laterWriteOptions = fetchMock.mock.calls[3]?.[1] as RequestInit;
    expect(new Headers(laterWriteOptions.headers).get("X-CSRF-Token")).toBe(
      "csrf-token-two",
    );
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

  it.each([
    ["network error", new Error("offline"), { code: "network_error" }],
    ["AbortError", Object.assign(new Error("cancelled"), { name: "AbortError" }), { name: "AbortError" }],
  ])("clears after logout %s when no newer session exists", async (_name, failure, expected) => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(authenticatedSession))
      .mockRejectedValueOnce(failure)
      .mockResolvedValueOnce(response(source));
    vi.stubGlobal("fetch", fetchMock);

    await login("admin", "password");
    await expect(logout()).rejects.toMatchObject(expected);
    await importSource("https://example.com/article");

    const laterWriteOptions = fetchMock.mock.calls[2]?.[1] as RequestInit;
    expect(new Headers(laterWriteOptions.headers).get("X-CSRF-Token")).toBeNull();
  });

  it("does not let a delayed logout clear a newer authentication generation", async () => {
    const delayedResponse = deferred<Response>();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(authenticatedSession))
      .mockReturnValueOnce(delayedResponse.promise)
      .mockResolvedValueOnce(response(rotatedSession))
      .mockResolvedValueOnce(response(source));
    vi.stubGlobal("fetch", fetchMock);

    await login("admin", "password");
    const pendingLogout = logout();
    const pendingLogin = login("admin", "password");
    delayedResponse.resolve(new Response(null, { status: 204 }));

    await expect(pendingLogout).resolves.toBeUndefined();
    await expect(pendingLogin).resolves.toEqual(rotatedSession);
    await importSource("https://example.com/new-request");

    const laterWriteOptions = fetchMock.mock.calls[3]?.[1] as RequestInit;
    expect(new Headers(laterWriteOptions.headers).get("X-CSRF-Token")).toBe(
      "csrf-token-two",
    );
  });

  it("waits for logout to settle before dispatching a newer login", async () => {
    const delayedLogout = deferred<Response>();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(authenticatedSession))
      .mockReturnValueOnce(delayedLogout.promise)
      .mockResolvedValueOnce(response(rotatedSession))
      .mockResolvedValueOnce(response(source));
    vi.stubGlobal("fetch", fetchMock);

    await login("admin", "password");
    const pendingLogout = logout();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const pendingLogin = login("admin", "password");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    delayedLogout.resolve(new Response(null, { status: 204 }));
    await expect(pendingLogout).resolves.toBeUndefined();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    await expect(pendingLogin).resolves.toEqual(rotatedSession);
    await importSource("https://example.com/new-request");

    const laterWriteOptions = fetchMock.mock.calls[3]?.[1] as RequestInit;
    expect(new Headers(laterWriteOptions.headers).get("X-CSRF-Token")).toBe(
      "csrf-token-two",
    );
  });

  it("does not let a stale session read overwrite a newer login token", async () => {
    const delayedSessionRead = deferred<Response>();
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(delayedSessionRead.promise)
      .mockResolvedValueOnce(response(rotatedSession))
      .mockResolvedValueOnce(response(source));
    vi.stubGlobal("fetch", fetchMock);

    const staleSessionRead = getCurrentSession();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await expect(login("admin", "password")).resolves.toEqual(rotatedSession);
    delayedSessionRead.resolve(response(authenticatedSession));

    await expect(staleSessionRead).resolves.toEqual(authenticatedSession);
    await importSource("https://example.com/new-request");

    const laterWriteOptions = fetchMock.mock.calls[2]?.[1] as RequestInit;
    expect(new Headers(laterWriteOptions.headers).get("X-CSRF-Token")).toBe(
      "csrf-token-two",
    );
  });

  it("serializes concurrent cookie-mutating authentication requests in invocation order", async () => {
    const firstResponse = deferred<Response>();
    const secondResponse = deferred<Response>();
    const thirdResponse = deferred<Response>();
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(firstResponse.promise)
      .mockReturnValueOnce(secondResponse.promise)
      .mockReturnValueOnce(thirdResponse.promise);
    vi.stubGlobal("fetch", fetchMock);

    const firstLogin = login("admin", "first password");
    const passwordChange = changePassword("first password", "second secure password");
    const secondLogin = login("admin", "second password");

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/auth/login");
    firstResponse.resolve(response(authenticatedSession));
    await expect(firstLogin).resolves.toEqual(authenticatedSession);

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1]?.[0]).toBe("/api/auth/change-password");
    secondResponse.resolve(response(rotatedSession));
    await expect(passwordChange).resolves.toEqual(rotatedSession);

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(fetchMock.mock.calls[2]?.[0]).toBe("/api/auth/login");
    thirdResponse.resolve(response(latestSession));
    await expect(secondLogin).resolves.toEqual(latestSession);
  });

  it("installs a queued login session before dispatching password change", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(authenticatedSession))
      .mockResolvedValueOnce(response(rotatedSession))
      .mockResolvedValueOnce(response(source));
    vi.stubGlobal("fetch", fetchMock);

    const pendingLogin = login("admin", "password");
    const pendingPasswordChange = changePassword("password", "new secure password");

    await expect(pendingLogin).resolves.toEqual(authenticatedSession);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const passwordChangeOptions = fetchMock.mock.calls[1]?.[1] as RequestInit;
    expect(passwordChangeOptions.body).toBe(
      JSON.stringify({ currentPassword: "password", newPassword: "new secure password" }),
    );
    expect(new Headers(passwordChangeOptions.headers).get("X-CSRF-Token")).toBe(
      "csrf-token-one",
    );
    await expect(pendingPasswordChange).resolves.toEqual(rotatedSession);
    await importSource("https://example.com/new-request");

    const laterWriteOptions = fetchMock.mock.calls[2]?.[1] as RequestInit;
    expect(new Headers(laterWriteOptions.headers).get("X-CSRF-Token")).toBe(
      "csrf-token-two",
    );
  });

  it("installs a queued login session before dispatching logout", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(authenticatedSession))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(response(source));
    vi.stubGlobal("fetch", fetchMock);

    const pendingLogin = login("admin", "password");
    const pendingLogout = logout();

    await expect(pendingLogin).resolves.toEqual(authenticatedSession);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const logoutOptions = fetchMock.mock.calls[1]?.[1] as RequestInit;
    expect(new Headers(logoutOptions.headers).get("X-CSRF-Token")).toBe("csrf-token-one");
    await expect(pendingLogout).resolves.toBeUndefined();
    await importSource("https://example.com/new-request");

    const laterWriteOptions = fetchMock.mock.calls[2]?.[1] as RequestInit;
    expect(new Headers(laterWriteOptions.headers).get("X-CSRF-Token")).toBeNull();
  });

  it("uses a replacement CSRF token for a queued second password change", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(authenticatedSession))
      .mockResolvedValueOnce(response(rotatedSession))
      .mockResolvedValueOnce(response(latestSession))
      .mockResolvedValueOnce(response(source));
    vi.stubGlobal("fetch", fetchMock);

    await login("admin", "password");
    const firstPasswordChange = changePassword("password", "second secure password");
    const secondPasswordChange = changePassword(
      "second secure password",
      "third secure password",
    );

    await expect(firstPasswordChange).resolves.toEqual(rotatedSession);
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const secondChangeOptions = fetchMock.mock.calls[2]?.[1] as RequestInit;
    expect(secondChangeOptions.body).toBe(
      JSON.stringify({
        currentPassword: "second secure password",
        newPassword: "third secure password",
      }),
    );
    expect(new Headers(secondChangeOptions.headers).get("X-CSRF-Token")).toBe(
      "csrf-token-two",
    );
    await expect(secondPasswordChange).resolves.toEqual(latestSession);
    await importSource("https://example.com/new-request");

    const laterWriteOptions = fetchMock.mock.calls[3]?.[1] as RequestInit;
    expect(new Headers(laterWriteOptions.headers).get("X-CSRF-Token")).toBe(
      "csrf-token-three",
    );
  });

  it("clears the CSRF token before dispatching a mutation queued after authentication loss", async () => {
    const authenticationRequiredResponse = () =>
      response(
        {
          detail: {
            code: "authentication_required",
            message: "Authentication is required.",
          },
        },
        401,
      );
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(authenticatedSession))
      .mockResolvedValueOnce(authenticationRequiredResponse())
      .mockResolvedValueOnce(authenticationRequiredResponse());
    vi.stubGlobal("fetch", fetchMock);

    await login("admin", "password");
    const failedPasswordChange = changePassword("password", "new secure password");
    const queuedLogout = logout();

    await expect(failedPasswordChange).rejects.toMatchObject({
      code: "authentication_required",
      status: 401,
    });
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const logoutOptions = fetchMock.mock.calls[2]?.[1] as RequestInit;
    expect(new Headers(logoutOptions.headers).get("X-CSRF-Token")).toBeNull();
    await expect(queuedLogout).rejects.toMatchObject({
      code: "authentication_required",
      status: 401,
    });
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
