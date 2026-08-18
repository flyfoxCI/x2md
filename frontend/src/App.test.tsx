import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import {
  changePassword,
  clearAuthentication,
  getCurrentSession,
  getSource,
  getSettings,
  importSource,
  listSources,
  login,
  logout,
  updateSettings,
} from "./api";
import type { AuthenticatedSession, Settings } from "./types";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  changePassword: vi.fn(),
  clearAuthentication: vi.fn(),
  getCurrentSession: vi.fn(),
  getSource: vi.fn(),
  listSources: vi.fn(),
  importSource: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  getSettings: vi.fn(),
  updateSettings: vi.fn(),
}));

const mockedChangePassword = vi.mocked(changePassword);
const mockedClearAuthentication = vi.mocked(clearAuthentication);
const mockedGetCurrentSession = vi.mocked(getCurrentSession);
const mockedGetSource = vi.mocked(getSource);
const mockedListSources = vi.mocked(listSources);
const mockedImportSource = vi.mocked(importSource);
const mockedLogin = vi.mocked(login);
const mockedLogout = vi.mocked(logout);
const mockedGetSettings = vi.mocked(getSettings);
const mockedUpdateSettings = vi.mocked(updateSettings);

const defaultSettings: Settings = {
  aiConfigured: false,
  presentation: { theme: "system" as const, preview_device: "desktop" as const },
};

const defaultSession: AuthenticatedSession = {
  user: { id: 1, username: "alice" },
  csrfToken: "csrf-test-token",
};

const emptySourcePage = {
  items: [],
  total: 0,
  page: 1,
  page_size: 20,
};

const importedSource = {
  id: 7,
  canonical_url: "https://github.com/example/reasoning",
  platform: "github",
  title: "Reasoning at Scale",
  author: "Ada Lovelace",
  published_at: null,
  raw_text: "Source material",
  source_markdown: "# Source material",
  metadata_json: {},
  import_status: "ready" as const,
  failure_reason: null,
  created_at: "2026-08-12T00:00:00Z",
  updated_at: "2026-08-12T00:00:00Z",
};

function deferred<T>() {
  let resolve: (value: T) => void;
  let reject: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve: resolve!, reject: reject! };
}

async function renderAuthenticatedApp() {
  const rendered = render(<App />);
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(screen.getByRole("button", { name: "打开知识库" })).toBeVisible();
  return rendered;
}

describe("App", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedChangePassword.mockResolvedValue(defaultSession);
    mockedGetCurrentSession.mockResolvedValue(defaultSession);
    mockedGetSettings.mockResolvedValue(defaultSettings);
    mockedListSources.mockResolvedValue(emptySourcePage);
    mockedLogin.mockResolvedValue(defaultSession);
    mockedLogout.mockResolvedValue(undefined);
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

    await renderAuthenticatedApp();

    expect(await screen.findByText("Reasoning at Scale")).toBeVisible();
    expect(mockedListSources).toHaveBeenCalledWith({}, expect.any(AbortSignal));
  });

  it("explains when an AI provider has not been configured", async () => {
    mockedListSources.mockRejectedValue({
      code: "provider_not_configured",
      message: "The AI provider is not configured.",
    });

    await renderAuthenticatedApp();

    expect(await screen.findByText(/AI 功能尚未配置/)).toBeVisible();
  });

  it("cancels the library request when the root unmounts without setting an error", async () => {
    let suppliedSignal: AbortSignal | undefined;
    mockedListSources.mockImplementation((_query, signal) => {
      suppliedSignal = signal;
      return new Promise(() => undefined);
    });

    const { unmount } = await renderAuthenticatedApp();
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

    const { unmount } = await renderAuthenticatedApp();
    unmount();

    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });

  it("renders an invalid response as a recoverable library error", async () => {
    mockedListSources.mockRejectedValue({
      code: "invalid_response",
      message: "服务返回的数据格式无效，请稍后重试。",
      status: 200,
    });

    await renderAuthenticatedApp();

    expect(await screen.findByRole("alert")).toHaveTextContent("数据格式无效");
  });

  it("hydrates non-secret presentation settings and persists theme and preview device selections", async () => {
    mockedGetSettings.mockResolvedValue({
      aiConfigured: false,
      presentation: { theme: "dark", preview_device: "mobile" },
    });
    await renderAuthenticatedApp();

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
    await renderAuthenticatedApp();

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
      await renderAuthenticatedApp();

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
      const { unmount } = await renderAuthenticatedApp();

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

  it("does not dispatch a queued presentation save after authentication expires", async () => {
    const firstSave = deferred<Settings>();
    mockedUpdateSettings.mockReturnValueOnce(firstSave.promise);
    await renderAuthenticatedApp();

    fireEvent.click(screen.getByRole("button", { name: "手机预览" }));
    await waitFor(() => expect(mockedUpdateSettings).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByLabelText("界面主题"), { target: { value: "light" } });

    await act(async () => {
      firstSave.reject({
        code: "authentication_required",
        message: "Authentication is required.",
        status: 401,
      });
      try {
        await firstSave.promise;
      } catch {
        // The component owns this expected rejection.
      }
    });

    expect(await screen.findByLabelText("用户名")).toBeVisible();
    await act(async () => {
      await Promise.resolve();
    });
    expect(mockedUpdateSettings).toHaveBeenCalledTimes(1);
  });

  it("sets the persisted system choice on the document for media-scoped theme tokens", async () => {
    await renderAuthenticatedApp();

    await waitFor(() => expect(document.documentElement).toHaveAttribute("data-theme", "system"));
    expect(screen.getByLabelText("界面主题")).toHaveValue("system");
  });

  it("keeps a local choice over a late read and gives an actionable message after bounded failures", async () => {
    vi.useFakeTimers();
    try {
      const initialSettings = deferred<typeof defaultSettings>();
      mockedGetSettings.mockReturnValue(initialSettings.promise);
      mockedUpdateSettings.mockRejectedValue({ code: "network_error", message: "do not expose internals" });
      await renderAuthenticatedApp();

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

    const { unmount } = await renderAuthenticatedApp();
    unmount();

    await waitFor(() => expect(suppliedSignal?.aborted).toBe(true));
  });

  it("does not load protected studio data before session recovery succeeds", async () => {
    const recoveringSession = deferred<AuthenticatedSession>();
    mockedGetCurrentSession.mockReturnValue(recoveringSession.promise);

    render(<App />);

    expect(screen.getByRole("status")).toHaveTextContent("正在恢复登录状态");
    expect(mockedListSources).not.toHaveBeenCalled();
    expect(mockedGetSettings).not.toHaveBeenCalled();

    await act(async () => {
      recoveringSession.resolve(defaultSession);
      await recoveringSession.promise;
    });

    expect(await screen.findByRole("button", { name: "打开知识库" })).toBeVisible();
    await waitFor(() => expect(mockedListSources).toHaveBeenCalledWith({}, expect.any(AbortSignal)));
    await waitFor(() => expect(mockedGetSettings).toHaveBeenCalledWith(expect.any(AbortSignal)));
  });

  it("keeps non-auth recovery failures out of the studio and can retry safely", async () => {
    mockedGetCurrentSession
      .mockRejectedValueOnce({ code: "network_error", message: "do not render transport detail" })
      .mockResolvedValueOnce(defaultSession);

    render(<App />);

    expect(await screen.findByRole("alert")).toHaveTextContent("无法恢复登录状态，请检查连接后重试。");
    expect(mockedListSources).not.toHaveBeenCalled();
    expect(mockedGetSettings).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "重试恢复登录" }));

    expect(await screen.findByRole("button", { name: "打开知识库" })).toBeVisible();
    expect(mockedListSources).toHaveBeenCalledTimes(1);
    expect(mockedGetSettings).toHaveBeenCalledTimes(1);
  });

  it("loads the studio after a successful login and keeps login failures generic", async () => {
    mockedGetCurrentSession.mockRejectedValue({
      code: "authentication_required",
      message: "Authentication is required.",
      status: 401,
    });
    mockedLogin
      .mockRejectedValueOnce({ code: "invalid_credentials", message: "password mismatch", status: 401 })
      .mockResolvedValueOnce(defaultSession);

    render(<App />);

    const username = await screen.findByLabelText("用户名");
    fireEvent.change(username, { target: { value: "alice" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "wrong-password" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("登录失败，请检查用户名和密码后重试。");
    expect(screen.queryByText("password mismatch")).not.toBeInTheDocument();
    expect(mockedListSources).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "correct-password" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByRole("button", { name: "打开知识库" })).toBeVisible();
    expect(mockedLogin).toHaveBeenLastCalledWith("alice", "correct-password");
    expect(mockedListSources).toHaveBeenCalledTimes(1);
    expect(mockedGetSettings).toHaveBeenCalledTimes(1);
  });

  it("opens account controls from the header and logs out to the login screen", async () => {
    await renderAuthenticatedApp();

    fireEvent.click(screen.getByRole("button", { name: "账户：alice" }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("alice");
    fireEvent.click(within(dialog).getByRole("button", { name: "退出登录" }));

    expect(await screen.findByLabelText("用户名")).toBeVisible();
    expect(mockedLogout).toHaveBeenCalledTimes(1);
    expect(mockedClearAuthentication).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "打开知识库" })).not.toBeInTheDocument();
  });

  it("returns to login without exposing details when header logout fails", async () => {
    mockedLogout.mockRejectedValue(new Error("internal logout transport detail"));
    await renderAuthenticatedApp();

    fireEvent.click(screen.getByRole("button", { name: "退出登录" }));

    expect(await screen.findByLabelText("用户名")).toBeVisible();
    expect(screen.queryByText("internal logout transport detail")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "打开知识库" })).not.toBeInTheDocument();
  });

  it("keeps the studio available after an invalid password update and closes after a successful update", async () => {
    mockedChangePassword
      .mockRejectedValueOnce({ code: "invalid_credentials", message: "current password mismatch", status: 401 })
      .mockResolvedValueOnce(defaultSession);
    await renderAuthenticatedApp();

    fireEvent.click(screen.getByRole("button", { name: "账户：alice" }));
    fireEvent.change(screen.getByLabelText("当前密码"), { target: { value: "wrong-current-password" } });
    fireEvent.change(screen.getByLabelText("新密码"), { target: { value: "new-secret-123" } });
    fireEvent.change(screen.getByLabelText("确认新密码"), { target: { value: "new-secret-123" } });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "更新密码" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("密码更新失败，请稍后重试。");
    expect(screen.getByRole("button", { name: "打开知识库" })).toBeVisible();

    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "更新密码" }));

    await waitFor(() => expect(mockedChangePassword).toHaveBeenLastCalledWith(
      "wrong-current-password",
      "new-secret-123",
    ));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "打开知识库" })).toBeVisible();
  });

  it("returns to login and removes studio controls when a running protected request expires", async () => {
    const pendingSources = deferred<typeof emptySourcePage>();
    mockedListSources.mockReturnValue(pendingSources.promise);
    await renderAuthenticatedApp();

    await act(async () => {
      pendingSources.reject({
        code: "authentication_required",
        message: "Authentication is required.",
        status: 401,
      });
      try {
        await pendingSources.promise;
      } catch {
        // The component owns this expected rejection.
      }
    });

    expect(await screen.findByLabelText("用户名")).toBeVisible();
    expect(mockedClearAuthentication).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "打开知识库" })).not.toBeInTheDocument();
  });

  it("ends the current session when an aborted source-detail request reports authentication_required", async () => {
    const firstDetail = deferred<{ source: typeof importedSource; artifacts: [] }>();
    const newerSource = {
      ...importedSource,
      id: 8,
      canonical_url: "https://github.com/example/newer-source",
      title: "Newer Source",
    };
    mockedListSources.mockResolvedValue({
      items: [importedSource, newerSource],
      total: 2,
      page: 1,
      page_size: 20,
    });
    mockedGetSource.mockImplementation((sourceId) => (
      sourceId === importedSource.id
        ? firstDetail.promise
        : Promise.resolve({ source: newerSource, artifacts: [] })
    ));
    await renderAuthenticatedApp();

    fireEvent.click(await screen.findByRole("button", { name: /Reasoning at Scale/ }));
    await waitFor(() => expect(mockedGetSource).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: /Newer Source/ }));
    expect(await screen.findByRole("heading", { name: "Newer Source" })).toBeVisible();
    expect(mockedGetSource.mock.calls[0]?.[1]?.aborted).toBe(true);

    await act(async () => {
      firstDetail.reject({
        code: "authentication_required",
        message: "Authentication is required.",
        status: 401,
      });
      try {
        await firstDetail.promise;
      } catch {
        // The canceled detail request still reports a global authentication failure.
      }
    });

    expect(await screen.findByLabelText("用户名")).toBeVisible();
    expect(mockedClearAuthentication).toHaveBeenCalledTimes(1);
  });

  it("keeps a newer login when an older protected request later reports authentication_required", async () => {
    const oldSessionRequest = deferred<typeof emptySourcePage>();
    const newerSession: AuthenticatedSession = {
      user: { id: 2, username: "bob" },
      csrfToken: "csrf-bob-token",
    };
    mockedListSources.mockReturnValueOnce(oldSessionRequest.promise);
    mockedLogin.mockResolvedValue(newerSession);
    await renderAuthenticatedApp();
    await waitFor(() => expect(mockedListSources).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "退出登录" }));
    expect(await screen.findByLabelText("用户名")).toBeVisible();

    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "bob" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "new-password" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    expect(await screen.findByRole("button", { name: "账户：bob" })).toBeVisible();

    await act(async () => {
      oldSessionRequest.reject({
        code: "authentication_required",
        message: "Authentication is required.",
        status: 401,
      });
      try {
        await oldSessionRequest.promise;
      } catch {
        // The stale operation is expected to reject after session B is active.
      }
    });

    expect(screen.getByRole("button", { name: "账户：bob" })).toBeVisible();
    expect(mockedClearAuthentication).toHaveBeenCalledTimes(1);
  });

  it("does not let an older logout revoke a newer login intent", async () => {
    const oldSessionRequest = deferred<typeof emptySourcePage>();
    const pendingLogout = deferred<void>();
    const newerSession: AuthenticatedSession = {
      user: { id: 2, username: "bob" },
      csrfToken: "csrf-bob-token",
    };
    mockedListSources.mockReturnValueOnce(oldSessionRequest.promise);
    mockedLogout.mockReturnValueOnce(pendingLogout.promise);
    mockedLogin.mockResolvedValue(newerSession);
    await renderAuthenticatedApp();
    await waitFor(() => expect(mockedListSources).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByLabelText("退出登录"));
    await waitFor(() => expect(mockedLogout).toHaveBeenCalledTimes(1));

    await act(async () => {
      oldSessionRequest.reject({
        code: "authentication_required",
        message: "Authentication is required.",
        status: 401,
      });
      try {
        await oldSessionRequest.promise;
      } catch {
        // The current session expires while the older logout is still queued.
      }
    });
    expect(await screen.findByLabelText("用户名")).toBeVisible();

    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "bob" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "new-password" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));
    expect(await screen.findByRole("button", { name: "账户：bob" })).toBeVisible();

    await act(async () => {
      pendingLogout.resolve(undefined);
      await pendingLogout.promise;
    });

    expect(screen.getByRole("button", { name: "账户：bob" })).toBeVisible();
  });

  it("converges to login when logout completes after a password rotation", async () => {
    const passwordChange = deferred<AuthenticatedSession>();
    const pendingLogout = deferred<void>();
    mockedChangePassword.mockReturnValueOnce(passwordChange.promise);
    mockedLogout.mockReturnValueOnce(pendingLogout.promise);
    await renderAuthenticatedApp();

    fireEvent.click(screen.getByRole("button", { name: "账户：alice" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(screen.getByLabelText("当前密码"), { target: { value: "current-secret" } });
    fireEvent.change(screen.getByLabelText("新密码"), { target: { value: "new-secret-123" } });
    fireEvent.change(screen.getByLabelText("确认新密码"), { target: { value: "new-secret-123" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "更新密码" }));
    await waitFor(() => expect(mockedChangePassword).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByLabelText("退出登录"));
    await waitFor(() => expect(mockedLogout).toHaveBeenCalledTimes(1));

    await act(async () => {
      passwordChange.resolve({
        user: defaultSession.user,
        csrfToken: "csrf-after-password-change",
      });
      await passwordChange.promise;
    });
    expect(screen.getByRole("button", { name: "打开知识库" })).toBeVisible();

    await act(async () => {
      pendingLogout.resolve(undefined);
      await pendingLogout.promise;
    });

    expect(await screen.findByLabelText("用户名")).toBeVisible();
  });

  it("stops an import follow-up when the refreshed library reports authentication_required", async () => {
    mockedImportSource.mockResolvedValue(importedSource);
    mockedListSources
      .mockResolvedValueOnce(emptySourcePage)
      .mockRejectedValueOnce({
        code: "authentication_required",
        message: "Authentication is required.",
        status: 401,
      });
    await renderAuthenticatedApp();
    await waitFor(() => expect(mockedListSources).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText("导入来源链接"), {
      target: { value: importedSource.canonical_url },
    });
    fireEvent.click(screen.getByRole("button", { name: "导入" }));

    expect(await screen.findByLabelText("用户名")).toBeVisible();
    expect(mockedGetSource).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "打开知识库" })).not.toBeInTheDocument();
  });
});
