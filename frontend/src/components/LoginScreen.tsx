import { useEffect, useRef, useState, type FormEvent } from "react";

interface LoginScreenProps {
  recoveryError?: string | null;
  onLogin: (username: string, password: string) => Promise<void>;
  onRetrySession?: () => void;
}

export function LoginScreen({ recoveryError, onLogin, onRetrySession }: LoginScreenProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const usernameRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    usernameRef.current?.focus();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!username.trim() || !password || submitting) {
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      await onLogin(username.trim(), password);
    } catch {
      setError("登录失败，请检查用户名和密码后重试。");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-shell">
      <form aria-label="登录" className="auth-card" onSubmit={(event) => void submit(event)}>
        <div className="auth-heading">
          <span aria-hidden="true" className="auth-mark">X²</span>
          <div>
            <h1>登录 X² Studio</h1>
            <p>使用你的账户继续访问专家内容知识库。</p>
          </div>
        </div>
        {recoveryError ? (
          <div className="auth-recovery-error" role="alert">
            <p>{recoveryError}</p>
            {onRetrySession ? (
              <button className="secondary-button" onClick={onRetrySession} type="button">重试恢复登录</button>
            ) : null}
          </div>
        ) : null}
        {error ? <p className="auth-form-error" role="alert">{error}</p> : null}
        <label htmlFor="login-username">用户名</label>
        <input
          autoComplete="username"
          id="login-username"
          onChange={(event) => setUsername(event.target.value)}
          ref={usernameRef}
          value={username}
        />
        <label htmlFor="login-password">密码</label>
        <input
          autoComplete="current-password"
          id="login-password"
          onChange={(event) => setPassword(event.target.value)}
          type="password"
          value={password}
        />
        <button className="primary-button auth-submit" disabled={submitting || !username.trim() || !password} type="submit">
          {submitting ? "登录中…" : "登录"}
        </button>
      </form>
    </main>
  );
}
