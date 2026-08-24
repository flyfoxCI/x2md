import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LoginScreen } from "./LoginScreen";

describe("LoginScreen", () => {
  it("labels and focuses credential fields without exposing the password", () => {
    render(<LoginScreen onLogin={vi.fn().mockResolvedValue(undefined)} />);

    const username = screen.getByLabelText("用户名");
    const password = screen.getByLabelText("密码");

    expect(username).toHaveFocus();
    expect(username).toHaveAttribute("autocomplete", "username");
    expect(password).toHaveAttribute("autocomplete", "current-password");
    expect(password).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "登录" })).toBeDisabled();
  });

  it("disables the form while pending and gives a generic failure message", async () => {
    let rejectLogin: (reason?: unknown) => void;
    const pendingLogin = new Promise<void>((_resolve, reject) => {
      rejectLogin = reject;
    });
    const onLogin = vi.fn().mockReturnValue(pendingLogin);
    render(<LoginScreen onLogin={onLogin} />);

    fireEvent.change(screen.getByLabelText("用户名"), { target: { value: "alice" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "not-shown" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(onLogin).toHaveBeenCalledWith("alice", "not-shown");
    expect(screen.getByRole("button", { name: "登录中…" })).toBeDisabled();

    rejectLogin!(new Error("backend credential detail must not be rendered"));

    expect(await screen.findByRole("alert")).toHaveTextContent("登录失败，请检查用户名和密码后重试。");
    expect(screen.queryByText("backend credential detail must not be rendered")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "登录" })).toBeEnabled());
  });
});
