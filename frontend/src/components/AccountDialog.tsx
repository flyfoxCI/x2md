import { useEffect, useRef, useState, type FormEvent } from "react";

import type { AuthenticatedUser } from "../types";

interface AccountDialogProps {
  user: AuthenticatedUser;
  trigger: HTMLElement | null;
  onChangePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  onClose: () => void;
  onLogout: () => Promise<void>;
}

export function AccountDialog({ user, trigger, onChangePassword, onClose, onLogout }: AccountDialogProps) {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [pendingAction, setPendingAction] = useState<"password" | "logout" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const currentPasswordRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    currentPasswordRef.current?.focus();
  }, []);

  function close() {
    trigger?.focus();
    onClose();
  }

  async function updatePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pendingAction) {
      return;
    }
    if (newPassword.length < 12) {
      setError("新密码至少需要 12 个字符。");
      return;
    }
    if (newPassword !== confirmation) {
      setError("两次输入的新密码不一致。");
      return;
    }

    setPendingAction("password");
    setError(null);
    try {
      await onChangePassword(currentPassword, newPassword);
      close();
    } catch {
      setError("密码更新失败，请稍后重试。");
    } finally {
      setPendingAction(null);
    }
  }

  async function logOut() {
    if (pendingAction) {
      return;
    }
    setPendingAction("logout");
    setError(null);
    try {
      await onLogout();
    } catch {
      setError("退出登录失败，请稍后重试。");
      setPendingAction(null);
    }
  }

  const pending = pendingAction !== null;

  return (
    <div aria-labelledby="account-dialog-title" aria-modal="true" className="dialog-scrim" role="dialog">
      <form aria-label="账户设置" className="account-dialog" onSubmit={(event) => void updatePassword(event)}>
        <div className="dialog-heading">
          <div>
            <h2 id="account-dialog-title">账户设置</h2>
            <p>已登录为 <strong>{user.username}</strong></p>
          </div>
          <button aria-label="关闭账户对话框" className="icon-button" disabled={pending} onClick={close} type="button">×</button>
        </div>
        {error ? <p className="auth-form-error" role="alert">{error}</p> : null}
        <label htmlFor="account-current-password">当前密码</label>
        <input
          autoComplete="current-password"
          disabled={pending}
          id="account-current-password"
          onChange={(event) => setCurrentPassword(event.target.value)}
          ref={currentPasswordRef}
          required
          type="password"
          value={currentPassword}
        />
        <label htmlFor="account-new-password">新密码</label>
        <input
          autoComplete="new-password"
          disabled={pending}
          id="account-new-password"
          minLength={12}
          onChange={(event) => setNewPassword(event.target.value)}
          required
          type="password"
          value={newPassword}
        />
        <label htmlFor="account-confirm-password">确认新密码</label>
        <input
          autoComplete="new-password"
          disabled={pending}
          id="account-confirm-password"
          minLength={12}
          onChange={(event) => setConfirmation(event.target.value)}
          required
          type="password"
          value={confirmation}
        />
        <div className="dialog-actions account-actions">
          <button className="secondary-button" disabled={pending} onClick={() => void logOut()} type="button">
            {pendingAction === "logout" ? "退出中…" : "退出登录"}
          </button>
          <button className="primary-button" disabled={pending} type="submit">
            {pendingAction === "password" ? "更新中…" : "更新密码"}
          </button>
        </div>
      </form>
    </div>
  );
}
