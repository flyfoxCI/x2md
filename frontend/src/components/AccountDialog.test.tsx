import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ComponentProps } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AccountDialog } from "./AccountDialog";

function renderDialog(overrides: Partial<ComponentProps<typeof AccountDialog>> = {}) {
  const trigger = document.createElement("button");
  trigger.textContent = "账户：alice";
  document.body.append(trigger);
  trigger.focus();
  const props = {
    user: { id: 1, username: "alice" },
    trigger,
    onChangePassword: vi.fn().mockResolvedValue(undefined),
    onClose: vi.fn(),
    onLogout: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
  render(<AccountDialog {...props} />);
  return { props, trigger };
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("AccountDialog", () => {
  it("shows the signed-in username and validates password confirmation and length locally", () => {
    const { props } = renderDialog();

    expect(screen.getByRole("dialog")).toHaveTextContent("alice");
    expect(screen.getByLabelText("当前密码")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByLabelText("新密码")).toHaveAttribute("autocomplete", "new-password");
    expect(screen.getByLabelText("确认新密码")).toHaveAttribute("autocomplete", "new-password");

    fireEvent.change(screen.getByLabelText("当前密码"), { target: { value: "current-secret" } });
    fireEvent.change(screen.getByLabelText("新密码"), { target: { value: "too-short" } });
    fireEvent.change(screen.getByLabelText("确认新密码"), { target: { value: "too-short" } });
    fireEvent.click(screen.getByRole("button", { name: "更新密码" }));

    expect(screen.getByRole("alert")).toHaveTextContent("新密码至少需要 12 个字符。");
    expect(props.onChangePassword).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("新密码"), { target: { value: "new-secret-123" } });
    fireEvent.change(screen.getByLabelText("确认新密码"), { target: { value: "different-secret" } });
    fireEvent.click(screen.getByRole("button", { name: "更新密码" }));

    expect(screen.getByRole("alert")).toHaveTextContent("两次输入的新密码不一致。");
    expect(props.onChangePassword).not.toHaveBeenCalled();
  });

  it("keeps service failures generic and restores trigger focus after a successful password update", async () => {
    const onChangePassword = vi.fn()
      .mockRejectedValueOnce(new Error("internal password policy detail"))
      .mockResolvedValueOnce(undefined);
    const { props, trigger } = renderDialog({ onChangePassword });

    fireEvent.change(screen.getByLabelText("当前密码"), { target: { value: "current-secret" } });
    fireEvent.change(screen.getByLabelText("新密码"), { target: { value: "new-secret-123" } });
    fireEvent.change(screen.getByLabelText("确认新密码"), { target: { value: "new-secret-123" } });
    fireEvent.click(screen.getByRole("button", { name: "更新密码" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("密码更新失败，请稍后重试。");
    expect(screen.queryByText("internal password policy detail")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "更新密码" }));

    await waitFor(() => expect(props.onChangePassword).toHaveBeenLastCalledWith("current-secret", "new-secret-123"));
    expect(props.onClose).toHaveBeenCalledTimes(1);
    expect(trigger).toHaveFocus();
  });
});
