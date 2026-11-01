import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { viewsApi, type Board, type BoardItem, type Run } from "../../lib/api";
import { label, num, pct, plural, shortDate } from "../../lib/format";
import { Badge, EmptyState, Notice, Segmented, Spinner } from "../../components/ui";
import { Quote } from "./Problems";
import { ReanalyzeNotice, SectionIntro, ShareBar, ThemeLink, TrendBadge } from "./shared";

type Kind = "bug" | "feature_request" | "ux_friction" | "complaint";

const KINDS: Record<Kind, { tab: string; title: string; guide: string }> = {
  bug: {
    tab: "Bugs to fix",
    title: "Bugs, ranked by reach and severity",
    guide: "Something is broken. High-severity bugs that are rising usually block a release or need a hotfix.",
  },
  feature_request: {
    tab: "Requests to build",
    title: "Feature requests, ranked by demand",
    guide: "Demand counts each request plus the helpful votes other users gave it. Treat as signals to validate, not specs.",
  },
  ux_friction: {
    tab: "UX friction to redesign",
    title: "UX friction, ranked by reach and negativity",
    guide: "Nothing is broken, but people struggle: confusing screens, too many steps, hard-to-find features. Usually a design fix.",
  },
  complaint: {
    tab: "Complaints to reconsider",
    title: "Complaints about policy, pricing, ads or content",
    guide: "Product or business decisions people dislike. Weigh them against goals rather than treating them as bugs.",
  },
};

function Item({ item, rank, kind }: { item: BoardItem; rank: number; kind: Kind }) {
  return (
    <li className="grid gap-3 border-b border-line py-5 md:grid-cols-[2rem_1fr]">
      <span className="text-lg font-semibold tabular-nums text-muted">{rank}</span>
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="font-semibold">
            <ThemeLink theme={item.theme} />
          </h3>
          <TrendBadge trend={item.trend} />
          {kind === "bug" && item.high_severity_share != null && item.high_severity_share >= 0.5 && <Badge tone="neg">Mostly high severity</Badge>}
        </div>
        <p className="text-sm text-muted">
          {plural(item.mentions, "review")}
          {item.helpful_votes > 0 && `, ${num(item.helpful_votes)} helpful votes from others`}, average {item.avg_rating}★
          {item.versions.length > 0 && `, mostly version ${item.versions[0].value}`}
          {item.first_seen && `, first seen ${shortDate(item.first_seen)}`}
        </p>
        {item.quotes[0] && <Quote review={item.quotes[0]} />}
      </div>
    </li>
  );
}

function BoardView({ board, kind, hasSeverity }: { board: Board; kind: Kind; hasSeverity: boolean }) {
  const high = board.severity.find((s) => s.value === "high");
  return (
    <section>
      <SectionIntro title={KINDS[kind].title}>{KINDS[kind].guide}</SectionIntro>
      <dl className="mb-2 flex flex-wrap gap-x-8 gap-y-2 text-sm">
        <div>
          <dt className="text-muted">Reviews</dt>
          <dd className="text-xl font-semibold tabular-nums">
            {num(board.count)} <span className="text-sm font-normal text-muted">({pct(board.share)} of analyzed)</span>
          </dd>
        </div>
        {kind === "bug" && hasSeverity && high && (
          <div>
            <dt className="text-muted">High severity</dt>
            <dd className="text-xl font-semibold tabular-nums text-neg">{pct(high.share)}</dd>
          </div>
        )}
        <div className="self-end pb-1">
          <TrendBadge trend={board.trend} />
        </div>
      </dl>
      {board.items.length === 0 ? (
        <p className="py-6 text-sm text-muted">No {label(kind).toLowerCase()} themes in these reviews.</p>
      ) : (
        <ol>
          {board.items.map((item, i) => (
            <Item key={item.theme} item={item} rank={i + 1} kind={kind} />
          ))}
        </ol>
      )}
    </section>
  );
}

export function FeedbackTab({ run }: { run: Run }) {
  const [kind, setKind] = useState<Kind>("bug");
  const data = useQuery({ queryKey: ["view-feedback", run.id], queryFn: () => viewsApi.feedback(run.id) });
  if (data.isLoading) return <Spinner />;
  if (data.error) return <Notice tone="error" title="Couldn't load feedback types">{data.error.message}</Notice>;
  const d = data.data!;
  if (d.total_tagged === 0) return <EmptyState title="These reviews haven't been analyzed by AI yet" />;

  return (
    <div className="flex flex-col gap-6">
      <div className="overflow-x-auto">
        <Segmented
          label="Feedback type"
          value={kind}
          onChange={setKind}
          options={(Object.keys(KINDS) as Kind[]).map((k) => ({ value: k, label: `${KINDS[k].tab} (${d.boards[k].count})` }))}
        />
      </div>
      <div className="grid gap-3 sm:grid-cols-4">
        {(Object.keys(KINDS) as Kind[]).map((k) => (
          <div key={k} className="flex flex-col gap-1">
            <span className="text-xs text-muted">{label(k)}</span>
            <ShareBar value={d.boards[k].share} tone={k === "bug" ? "neg" : "ink"} />
          </div>
        ))}
      </div>
      {kind === "bug" && !d.has_severity && <ReanalyzeNotice run={run} what="bug severity" />}
      <BoardView board={d.boards[kind]} kind={kind} hasSeverity={d.has_severity} />
    </div>
  );
}
