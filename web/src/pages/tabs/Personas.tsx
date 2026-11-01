import type { Run } from "../../lib/api";
import { Notice } from "../../components/ui";
import { ArtifactFrame, Evidence } from "./ArtifactFrame";

function List({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h4 className="mb-1 text-xs font-medium text-muted">{title}</h4>
      <ul className="list-disc space-y-0.5 pl-5 text-sm">{items.map((i) => <li key={i}>{i}</li>)}</ul>
    </div>
  );
}

export function PersonasTab({ run }: { run: Run }) {
  return (
    <ArtifactFrame
      run={run}
      kind="personas"
      title="Proto-personas"
      description="Drafts 2–4 personas from the language in these reviews: who they are, goals, frustrations, behaviours and what that means for design. They're hypotheses to validate with research, not facts."
      generateLabel="Draft personas"
    >
      {(artifact) => (
        <div className="flex flex-col gap-4">
          <Notice title="Hypotheses, not research findings">
            These come only from app store reviews, which over-represent strong opinions. Validate them with interviews
            or analytics before relying on them.
          </Notice>
          <div className="grid gap-4 lg:grid-cols-2">
            {artifact.content.personas.map((p) => (
              <article key={p.name} className="flex flex-col gap-3 rounded-lg border border-line bg-panel p-5">
                <header>
                  <h3 className="font-quote text-xl font-semibold">{p.name}</h3>
                  <p className="text-sm text-muted">{p.who}</p>
                  {p.how_common && <p className="mt-1 text-xs text-muted">{p.how_common}</p>}
                </header>
                <List title="Goals" items={p.goals} />
                <List title="Frustrations" items={p.frustrations} />
                <List title="Behaviours" items={p.behaviours} />
                <List title="What it means for design" items={p.design_implications} />
                <Evidence ids={p.review_ids} reviews={artifact.content.reviews} max={1} clamp />
              </article>
            ))}
          </div>
        </div>
      )}
    </ArtifactFrame>
  );
}
