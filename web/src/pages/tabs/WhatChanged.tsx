import type { Run } from "../../lib/api";
import { Badge, Panel } from "../../components/ui";
import { ArtifactFrame, Evidence } from "./ArtifactFrame";

const KIND = {
  new: { label: "New", tone: "warn" },
  worse: { label: "Worse", tone: "neg" },
  better: { label: "Better", tone: "pos" },
  steady: { label: "Unchanged", tone: "neutral" },
} as const;

export function WhatChangedPanel({ run }: { run: Run }) {
  return (
    <Panel>
      <ArtifactFrame
        run={run}
        kind="what_changed"
        title="What changed"
        description="Get a written summary of what got better or worse in the latest app version (or the newer half of these reviews)."
        generateLabel="Summarize what changed"
        compact
      >
        {(artifact) => {
          const c = artifact.content;
          return (
            <div className="flex flex-col gap-4">
              <p className="font-quote text-lg leading-snug">{c.headline}</p>
              {c.compared && <p className="-mt-2 text-xs text-muted">Compared: {c.compared}</p>}
              <ul className="flex flex-col gap-4">
                {c.changes.map((change) => (
                  <li key={`${change.kind}-${change.theme}`} className="flex flex-col gap-2">
                    <div className="flex items-baseline gap-2">
                      <Badge tone={KIND[change.kind].tone}>{KIND[change.kind].label}</Badge>
                      <span className="font-medium">{change.theme}</span>
                    </div>
                    <p className="text-sm">{change.detail}</p>
                    <Evidence ids={change.review_ids} reviews={c.reviews} max={1} />
                  </li>
                ))}
              </ul>
              {c.next_step && (
                <p className="rounded-md bg-soft px-3 py-2 text-sm">
                  <span className="font-medium">Next step: </span>
                  {c.next_step}
                </p>
              )}
            </div>
          );
        }}
      </ArtifactFrame>
    </Panel>
  );
}
