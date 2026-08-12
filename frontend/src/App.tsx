import { useEffect, useState } from "react";

import { isAbortError, isApiError, listSources } from "./api";
import type { ApiError, Source } from "./types";
import "./styles/app.css";

const providerNotConfiguredMessage =
  "AI 功能尚未配置。你仍可导入、浏览和整理来源；配置服务端 AI 后即可生成翻译、摘要和 Skill。";

function App() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    void listSources({}, controller.signal)
      .then((page) => {
        if (active) {
          setSources(page.items);
          setError(null);
        }
      })
      .catch((reason: unknown) => {
        if (active && !isAbortError(reason)) {
          setError(
            isApiError(reason)
              ? reason
              : {
                  code: "network_error",
                  message: "无法连接到知识库服务，请确认服务正在运行。",
                },
          );
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  return (
    <main className="app-shell">
      <header className="app-header">
        <h1>X² Studio</h1>
        <p>专家内容知识库</p>
      </header>
      <section aria-labelledby="library-title" className="library-state">
        <h2 id="library-title">知识库</h2>
        {loading ? <p role="status">正在加载来源…</p> : null}
        {error ? (
          <p className="error-state" role="alert">
            {error.code === "provider_not_configured"
              ? providerNotConfiguredMessage
              : error.message}
          </p>
        ) : null}
        {!loading && !error && sources.length === 0 ? (
          <p>还没有已导入的来源。</p>
        ) : null}
        <ul className="source-list">
          {sources.map((source) => (
            <li key={source.id}>
              <a href={source.canonical_url} rel="noreferrer" target="_blank">
                {source.title}
              </a>
              <span>{source.platform}</span>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}

export default App;
