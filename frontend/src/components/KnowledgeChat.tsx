import { useEffect, useRef, useState, type FormEvent } from "react";

import { artifactDownloadUrl, chatWithSource, isAbortError, isApiError } from "../api";
import type { ApiError, ChatTurn, Source } from "../types";
import { SafeMarkdown } from "./SafeMarkdown";
import { isSafeHttpsUrl } from "./safeUrl";

interface KnowledgeChatProps {
  source: Source | null;
}

const chatErrorCopy: Record<string, string> = {
  provider_not_configured: "AI 功能尚未配置。配置服务端 AI 后即可基于该来源回答问题。",
  provider_error: "AI 服务暂时未能完成回答，请稍后重试。",
  source_unavailable: "当前来源没有足够的可用材料，暂时无法回答。",
  restricted_source: "该来源受访问限制，无法据此生成可靠回答。",
  network_error: "无法连接到知识库服务，请确认服务正在运行。",
};

function asApiError(reason: unknown): ApiError {
  if (isApiError(reason)) {
    return reason;
  }
  return { code: "network_error", message: chatErrorCopy.network_error };
}

export function KnowledgeChat({ source }: KnowledgeChatProps) {
  const [question, setQuestion] = useState("");
  const [turn, setTurn] = useState<ChatTurn | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const requestRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    requestRef.current?.abort();
    requestRef.current = null;
    requestIdRef.current += 1;
    setQuestion("");
    setTurn(null);
    setError(null);
    setSubmitting(false);
  }, [source?.id]);

  useEffect(() => () => requestRef.current?.abort(), []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const sourceId = source?.id;
    const trimmedQuestion = question.trim();
    if (!sourceId || !trimmedQuestion || submitting) {
      return;
    }

    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setSubmitting(true);
    setError(null);

    try {
      const answer = await chatWithSource(sourceId, trimmedQuestion, controller.signal);
      if (controller.signal.aborted || requestId !== requestIdRef.current) {
        return;
      }
      setTurn(answer);
      setQuestion("");
    } catch (reason) {
      if (controller.signal.aborted || requestId !== requestIdRef.current || isAbortError(reason)) {
        return;
      }
      setTurn(null);
      setError(asApiError(reason));
    } finally {
      if (requestId === requestIdRef.current) {
        setSubmitting(false);
      }
    }
  }

  const errorMessage = error ? chatErrorCopy[error.code] ?? error.message : null;

  return (
    <section aria-label="来源助手" className="knowledge-chat">
      <div className="knowledge-chat-heading">
        <div>
          <h2>来源助手</h2>
          <p>{source ? "仅依据当前来源与其知识版本" : "请先选择一个来源"}</p>
        </div>
      </div>
      <form className="knowledge-chat-form" onSubmit={(event) => void submit(event)}>
        <label className="sr-only" htmlFor="source-question">向来源提问</label>
        <textarea
          disabled={!source || submitting}
          id="source-question"
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={source ? "例如：这个方法适合什么场景？" : "选择来源后即可提问"}
          rows={2}
          value={question}
        />
        <button className="primary-button" disabled={!source || submitting || !question.trim()} type="submit">
          {submitting ? "回答中…" : "发送问题"}
        </button>
      </form>
      {errorMessage ? <p className="chat-error" role="alert">{errorMessage}</p> : null}
      {turn ? (
        <div className="chat-turn" aria-live="polite">
          <p className="chat-question">{turn.question}</p>
          <div className="chat-answer"><SafeMarkdown>{turn.answer_markdown}</SafeMarkdown></div>
          <ul aria-label="回答引用" className="chat-citations">
            {turn.citations_json.map((citation, index) => (
              <li key={`${citation.source_id}-${citation.artifact_id ?? "source"}-${citation.url}-${index}`}>
                {isSafeHttpsUrl(citation.url) ? (
                  <a href={citation.url} rel="noopener noreferrer" target="_blank">
                    原始来源：{citation.section}
                  </a>
                ) : <>原始来源：{citation.section}</>}
                {citation.artifact_id !== null ? (
                  <a href={artifactDownloadUrl(citation.artifact_id)}>引用版本 #{citation.artifact_id}</a>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
