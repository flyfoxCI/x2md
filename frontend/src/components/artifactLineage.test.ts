import { describe, expect, it } from "vitest";

import type { Artifact } from "../types";
import { rootArtifactKind } from "./artifactLineage";

const research: Artifact = {
  id: 1,
  source_id: 1,
  kind: "research",
  title: "Research",
  markdown: "report",
  language: "zh",
  parent_artifact_id: null,
  model_metadata_json: {},
  created_at: "2026-08-30T00:00:00Z",
  updated_at: "2026-08-30T00:00:00Z",
};

describe("rootArtifactKind", () => {
  it("keeps one lineage owner for research user edits", () => {
    const edit: Artifact = { ...research, id: 2, kind: "user_edit", parent_artifact_id: 1 };

    expect(rootArtifactKind(edit, new Map([[research.id, research], [edit.id, edit]]))).toBe("research");
  });

  it("fails closed for a user edit whose parent is unavailable", () => {
    const edit: Artifact = { ...research, id: 2, kind: "user_edit", parent_artifact_id: 99 };

    expect(rootArtifactKind(edit, new Map([[edit.id, edit]]))).toBe("user_edit");
  });
});
