import type { Artifact, ArtifactKind } from "../types";

/** Resolve an append-only edit chain to the artifact kind that owns its behavior. */
export function rootArtifactKind(
  artifact: Artifact,
  byId: ReadonlyMap<number, Artifact>,
): ArtifactKind {
  let current = artifact;
  const visited = new Set<number>();
  while (current.kind === "user_edit" && current.parent_artifact_id !== null && !visited.has(current.id)) {
    visited.add(current.id);
    const parent = byId.get(current.parent_artifact_id);
    if (!parent) break;
    current = parent;
  }
  return current.kind;
}
