import type { ReactNode } from "react";
import { Link } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Sparkles } from "lucide-react";
import { artifactsApi, type Artifact, type ArtifactKind, type CitedReviewFull, type Review, type Run } from "../../lib/api";
import { relativeTime } from "../../lib/format";
import { toLLMConfig, useConnection } from "../../lib/settings";
import { Button, EmptyState, Notice, Spinner } from "../../components/ui";
import { Quote } from "./Problems";

/** Quotes for cited review IDs (only reviews the backend verified are present). */
export function Evidence({
  ids,
  reviews,
  max = 2,
  clamp = false,
}: {
  ids: string[];
  reviews: Record<string, CitedReviewFull>;
  max?: number;
  clamp?: boolean;
}) {
  const found = ids.map((id) => reviews[id]).filter(Boolean).slice(0, max);
  if (found.length === 0) return null;
  return (
    <div className="flex flex-col gap-3">
      {found.map((r) => (
        <Quote key={r.review_id} review={r as unknown as Review} clamp={clamp} />
      ))}
    </div>
  );
}

/** Loads a saved artifact, or offers to generate it; handles regenerate, errors and the waiting state. */
export function ArtifactFrame<K extends ArtifactKind>({
  run,
  kind,
  title,
  description,
  generateLabel,
  compact = false,
  children,
}: {
  run: Run;
  kind: K;
  title: string;
  description: string;
  generateLabel: string;
  compact?: boolean;
  children: (artifact: Artifact<K>) => ReactNode;
}) {
  const queryClient = useQueryClient();
  const { connection, ready, provider, modelLabel } = useConnection();
  const key = ["artifact", run.id, kind];
  const saved = useQuery({ queryKey: key, queryFn: () => artifactsApi.get(run.id, kind) });
  const generate = useMutation({
    mutationFn: () => artifactsApi.generate(run.id, kind, toLLMConfig(connection!)),
    onSuccess: (data) => queryClient.setQueryData(key, data),
  });
  const artifact = saved.data?.artifact;
  const legacy = run.provider === "legacy";

  if (saved.isLoading) return <Spinner />;

  const generateButton = (
    <Button
      variant={artifact ? "secondary" : "primary"}
      size={artifact ? "sm" : "md"}
      onClick={() => generate.mutate()}
      busy={generate.isPending}
      disabled={!ready || legacy}
      className="print:hidden"
    >
      {artifact ? <RefreshCw className="size-4" aria-hidden /> : <Sparkles className="size-4" aria-hidden />}
      {artifact ? "Regenerate" : generateLabel}
    </Button>
  );

  return (
    <section className="flex flex-col gap-5" aria-label={title}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className={compact ? "font-semibold" : "text-lg font-semibold"}>{title}</h2>
          {artifact ? (
            <p className="mt-0.5 text-xs text-muted">
              Written by {artifact.model} {relativeTime(artifact.created_at)}. Every point cites real reviews.
            </p>
          ) : (
            !compact && <p className="mt-1 max-w-prose text-sm text-muted">{description}</p>
          )}
        </div>
        {artifact && generateButton}
      </header>

      {generate.isPending && <Spinner label={`Writing with ${modelLabel || "your model"}. This usually takes 10–30 seconds.`} />}
      {generate.isError && <Notice tone="error" title="Couldn't write this">{generate.error.message}</Notice>}

      {artifact
        ? !generate.isPending && children(artifact)
        : !generate.isPending && (
            <EmptyState title={compact ? description : `No ${title.toLowerCase()} yet`}>
              <p>
                {legacy
                  ? "This analysis came from the previous version and lacks the tags these need. Run it again first."
                  : ready
                    ? `Uses ${provider?.name} ${modelLabel}. Built only from this analysis, with quotes as evidence.`
                    : "Connect an AI model first."}
              </p>
              <div className="mt-3 flex gap-2">
                {ready ? (
                  generateButton
                ) : (
                  <Link to="/settings" className="font-medium text-ink underline underline-offset-2">
                    Connect a model
                  </Link>
                )}
              </div>
            </EmptyState>
          )}
    </section>
  );
}
