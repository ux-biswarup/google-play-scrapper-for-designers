import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown } from "lucide-react";
import { artifactsApi, type CitedReviewFull, type Decision, type DecisionStatus, type Run } from "../../lib/api";
import { Badge, Segmented, Select, cx } from "../../components/ui";
import { ArtifactFrame, Evidence } from "./ArtifactFrame";
import { ThemeLink } from "./shared";

const BUCKETS = [
  { id: "now", label: "Now", hint: "High impact, solid evidence, reasonable effort" },
  { id: "next", label: "Next", hint: "Worth planning soon" },
  { id: "later", label: "Later", hint: "Lower impact or costly; revisit" },
] as const;

const STATUSES: { value: DecisionStatus; label: string }[] = [
  { value: "todo", label: "To do" },
  { value: "planned", label: "Planned" },
  { value: "in_progress", label: "In progress" },
  { value: "done", label: "Done" },
  { value: "dismissed", label: "Dismissed" },
];

const ACTION_LABEL: Record<string, string> = {
  fix: "Fix",
  redesign: "Redesign",
  build: "Build",
  reconsider: "Reconsider",
  protect: "Protect",
  investigate: "Investigate",
};

function Level({ label, value }: { label: string; value: string }) {
  return (
    <span className="text-xs text-muted">
      {label} <span className="font-medium text-ink">{value}</span>
    </span>
  );
}

function DecisionCard({ decision, reviews, runId }: { decision: Decision; reviews: Record<string, CitedReviewFull>; runId: string }) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const status = useMutation({
    mutationFn: (value: DecisionStatus) => artifactsApi.setStatus(runId, decision.id, value),
    onSuccess: (data) => queryClient.setQueryData(["artifact", runId, "decisions"], data),
  });
  const faded = decision.status === "done" || decision.status === "dismissed";

  return (
    <article className={cx("flex flex-col gap-3 rounded-lg border border-line bg-panel p-4", faded && "opacity-60")}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={decision.lens === "design" ? "warn" : "neutral"}>{decision.lens === "design" ? "Design" : "Product"}</Badge>
        <Badge tone={decision.action === "protect" ? "pos" : "neutral"}>{ACTION_LABEL[decision.action] ?? decision.action}</Badge>
        {decision.theme && (
          <span className="text-xs text-muted">
            <ThemeLink theme={decision.theme} />
          </span>
        )}
      </div>
      <h3 className="font-semibold leading-snug">{decision.title}</h3>
      <p className="text-sm">{decision.problem}</p>
      <p className="text-xs text-muted">{decision.evidence}</p>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        <Level label="Impact" value={decision.impact} />
        <Level label="Confidence" value={decision.confidence} />
        <Level label="Effort" value={decision.effort} />
      </div>
      <Evidence ids={decision.review_ids} reviews={reviews} max={1} clamp />

      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex items-center gap-1 self-start text-sm font-medium print:hidden"
      >
        <ChevronDown className={cx("size-4 transition-transform", open && "rotate-180")} aria-hidden />
        {open ? "Hide details" : "Causes, ideas and what to measure"}
      </button>
      {open && (
        <dl className="flex flex-col gap-3 border-t border-line pt-3 text-sm">
          {decision.who && (
            <div>
              <dt className="text-xs font-medium text-muted">Who is affected</dt>
              <dd>{decision.who}</dd>
            </div>
          )}
          {decision.root_causes.length > 0 && (
            <div>
              <dt className="text-xs font-medium text-muted">Likely causes (hypotheses)</dt>
              <dd>
                <ul className="list-disc pl-5">{decision.root_causes.map((c) => <li key={c}>{c}</li>)}</ul>
              </dd>
            </div>
          )}
          {decision.how_might_we.length > 0 && (
            <div>
              <dt className="text-xs font-medium text-muted">How might we</dt>
              <dd>
                <ul className="list-disc pl-5">{decision.how_might_we.map((q) => <li key={q}>{q}</li>)}</ul>
              </dd>
            </div>
          )}
          {decision.options.length > 0 && (
            <div>
              <dt className="text-xs font-medium text-muted">Options</dt>
              <dd>
                <ul className="flex flex-col gap-1">
                  {decision.options.map((o) => (
                    <li key={o.idea} className="flex items-start justify-between gap-3">
                      <span>{o.idea}</span>
                      <span className="shrink-0 text-xs text-muted">{o.effort} effort</span>
                    </li>
                  ))}
                </ul>
              </dd>
            </div>
          )}
          {decision.metric && (
            <div>
              <dt className="text-xs font-medium text-muted">Measure after shipping</dt>
              <dd>{decision.metric}</dd>
            </div>
          )}
          {decision.risk_of_inaction && (
            <div>
              <dt className="text-xs font-medium text-muted">If nothing changes</dt>
              <dd>{decision.risk_of_inaction}</dd>
            </div>
          )}
        </dl>
      )}

      <div className="mt-auto flex items-center gap-2 pt-1 print:hidden">
        <label htmlFor={`status-${decision.id}`} className="text-xs text-muted">
          Status
        </label>
        <Select
          id={`status-${decision.id}`}
          value={decision.status}
          onChange={(e) => status.mutate(e.target.value as DecisionStatus)}
          className="h-8 w-40 text-sm"
        >
          {STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </Select>
      </div>
    </article>
  );
}

export function DecisionsTab({ run }: { run: Run }) {
  const [lens, setLens] = useState<"all" | "design" | "product">("all");
  return (
    <ArtifactFrame
      run={run}
      kind="decisions"
      title="Decisions"
      description="Turns this analysis into ranked decisions: what designers should fix or redesign and what the product team should fix, build, reconsider or protect. Each comes with evidence, likely causes, How Might We questions, options and a metric to watch."
      generateLabel="Suggest decisions"
    >
      {(artifact) => {
        const all = artifact.content.decisions;
        const shown = all.filter((d) => lens === "all" || d.lens === lens);
        return (
          <div className="flex flex-col gap-5">
            <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
              <Segmented
                label="Lens"
                value={lens}
                onChange={setLens}
                options={[
                  { value: "all", label: `All (${all.length})` },
                  { value: "design", label: `Design (${all.filter((d) => d.lens === "design").length})` },
                  { value: "product", label: `Product (${all.filter((d) => d.lens === "product").length})` },
                ]}
              />
              <p className="text-xs text-muted">Priority = impact × confidence ÷ effort</p>
            </div>
            <div className="grid gap-4 xl:grid-cols-3">
              {BUCKETS.map((bucket) => {
                const items = shown.filter((d) => d.priority === bucket.id);
                return (
                  <section key={bucket.id} aria-labelledby={`bucket-${bucket.id}`} className="flex flex-col gap-3">
                    <header>
                      <h3 id={`bucket-${bucket.id}`} className="font-semibold">
                        {bucket.label} <span className="text-sm font-normal text-muted">{items.length}</span>
                      </h3>
                      <p className="text-xs text-muted">{bucket.hint}</p>
                    </header>
                    {items.length === 0 ? (
                      <p className="rounded-lg border border-dashed border-line p-4 text-sm text-muted">Nothing here.</p>
                    ) : (
                      items.map((d) => <DecisionCard key={d.id} decision={d} reviews={artifact.content.reviews} runId={run.id} />)
                    )}
                  </section>
                );
              })}
            </div>
          </div>
        );
      }}
    </ArtifactFrame>
  );
}
