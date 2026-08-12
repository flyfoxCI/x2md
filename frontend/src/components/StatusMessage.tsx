import type { ApiError, Source } from "../types";

interface StatusMessageProps {
  error?: ApiError | null;
  source?: Source | null;
  success?: string | null;
}

const restrictionCopy: Record<string, string> = {
  provider_not_configured:
    "AI 功能尚未配置。你仍可导入、浏览和整理来源；配置服务端 AI 后即可生成翻译、摘要和 Skill。",
  restricted_source: "该来源受访问限制，未保存未经验证的内容。请检查公开访问权限。",
  unsupported_url: "请输入受支持的公开 HTTPS 链接。",
  transcript_unavailable: "该视频已保存元数据，但公开字幕不可用。",
  source_unavailable: "暂时无法读取来源，请稍后重试。",
  network_error: "无法连接到知识库服务，请确认服务正在运行。",
};

function sourceStatus(source: Source): string | null {
  if (source.import_status === "partial") {
    return restrictionCopy[source.failure_reason ?? ""] ?? "部分导入：部分公开内容暂不可用。";
  }
  if (source.import_status === "blocked") {
    return restrictionCopy[source.failure_reason ?? ""] ?? "该来源无法导入。";
  }
  return null;
}

export function StatusMessage({ error, source, success }: StatusMessageProps) {
  const sourceCopy = source ? sourceStatus(source) : null;
  const errorCopy = error
    ? restrictionCopy[error.code] ?? error.message
    : null;
  const message = errorCopy ?? sourceCopy;

  if (success) {
    return <p className="status-message is-success" role="status">{success}</p>;
  }
  if (!message) {
    return null;
  }

  return (
    <p className="status-message is-warning" role="alert">
      {message}
    </p>
  );
}
