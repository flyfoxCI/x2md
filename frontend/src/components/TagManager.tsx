import { useMemo, useState } from "react";

import type { TagAssignment, TagDefinition } from "../types";

interface TagManagerProps {
  assignments: TagAssignment[];
  definitions: TagDefinition[];
  pending: boolean;
  onDecision: (assignmentId: number, status: "accepted" | "rejected") => void;
  onCreate: (label: string) => void;
  onDelete: (assignmentId: number) => void;
}

export function TagManager({ assignments, definitions, pending, onDecision, onCreate, onDelete }: TagManagerProps) {
  const [label, setLabel] = useState("");
  const labels = useMemo(() => new Map(definitions.map((item) => [item.id, item.label])), [definitions]);
  const accepted = assignments.filter((item) => item.status === "accepted");
  const suggested = assignments.filter((item) => item.status === "suggested");
  const submit = () => {
    const candidate = label.trim();
    if (!candidate || pending) return;
    onCreate(candidate);
    setLabel("");
  };

  return (
    <section aria-label="标签治理" className="tag-manager">
      <div className="tag-heading"><strong>标签治理</strong><span>已接受标签用于检索</span></div>
      <div className="tag-group"><span>已接受</span>{accepted.length ? accepted.map((item) => <div className="tag-row" key={item.id}><b>{labels.get(item.tag_id) ?? `Tag ${item.tag_id}`}</b><button aria-label={`移除 ${labels.get(item.tag_id) ?? item.tag_id}`} disabled={pending} onClick={() => onDelete(item.id)} type="button">移除</button></div>) : <em>暂无</em>}</div>
      <div className="tag-group"><span>AI 建议</span>{suggested.length ? suggested.map((item) => <div className="tag-row" key={item.id}><b>{labels.get(item.tag_id) ?? `Tag ${item.tag_id}`}</b><small>{item.confidence === null ? "" : `${Math.round(item.confidence * 100)}%`}</small><button aria-label={`接受 ${labels.get(item.tag_id) ?? item.tag_id}`} disabled={pending} onClick={() => onDecision(item.id, "accepted")} type="button">接受</button><button aria-label={`拒绝 ${labels.get(item.tag_id) ?? item.tag_id}`} disabled={pending} onClick={() => onDecision(item.id, "rejected")} type="button">拒绝</button></div>) : <em>暂无建议</em>}</div>
      <div className="tag-create"><label htmlFor="new-tag">新标签</label><input id="new-tag" onChange={(event) => setLabel(event.target.value)} value={label} /><button disabled={pending || !label.trim()} onClick={submit} type="button">添加标签</button></div>
    </section>
  );
}
