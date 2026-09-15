import { useMemo } from "react";

import type { TagAssignment, TagDefinition } from "../types";

interface TagManagerProps {
  assignments: TagAssignment[];
  definitions: TagDefinition[];
}

export function TagManager({ assignments, definitions }: TagManagerProps) {
  const labels = useMemo(() => new Map(definitions.map((item) => [item.id, item.label])), [definitions]);

  if (!assignments.length) return null;

  return (
    <section aria-label="自动标签" className="tag-manager">
      <div className="tag-chips">
        {assignments.map((item) => (
          <span
            className={item.status === "accepted" ? "tag-chip is-accepted" : "tag-chip is-suggested"}
            key={item.id}
            title={item.status === "suggested" ? "AI 建议" : undefined}
          >
            {labels.get(item.tag_id) ?? `Tag ${item.tag_id}`}
          </span>
        ))}
      </div>
    </section>
  );
}
