import { useMemo } from "react";
import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import type { Data } from "plotly.js";
import { api, type Run } from "../../lib/api";
import { label, num, pct, plural, rating, shortDate } from "../../lib/format";
import { Plot, useChartColors } from "../../components/Plot";
import { Notice, Panel, Spinner, Stars } from "../../components/ui";

function ImageLink({ run, chart }: { run: Run; chart: string }) {
  return (
    <a
      href={api.chartUrl(run.id, chart)}
      download
      className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink"
      title="Download as an image for slides and reports"
    >
      <Download className="size-4" aria-hidden /> Image
    </a>
  );
}

function BarList({ rows, color, labelOf }: { rows: { key: string; count: number }[]; color: string; labelOf: (k: string) => string }) {
  const data = useMemo<Data[]>(() => {
    const sorted = [...rows].sort((a, b) => a.count - b.count);
    return [
      {
        type: "bar",
        orientation: "h",
        x: sorted.map((r) => r.count),
        y: sorted.map((r) => labelOf(r.key)),
        marker: { color },
        hovertemplate: "%{y}: %{x} reviews<extra></extra>",
      },
    ];
  }, [rows, color, labelOf]);
  if (rows.length === 0) return <p className="text-sm text-muted">Not available for this analysis.</p>;
  return <Plot data={data} label="Bar chart" height={Math.max(160, rows.length * 30 + 30)} />;
}

export function OverviewTab({ run }: { run: Run }) {
  const colors = useChartColors();
  const overview = useQuery({ queryKey: ["overview", run.id], queryFn: () => api.overview(run.id) });
  const board = useQuery({ queryKey: ["themes", run.id], queryFn: () => api.themes(run.id) });

  const ratingData = useMemo<Data[]>(() => {
    const dist = overview.data?.rating_distribution ?? [];
    const palette = [colors.neg, colors.warn, colors.neu, colors.pos, colors.pos];
    return [
      {
        type: "bar",
        x: dist.map((d) => `${d.rating}★`),
        y: dist.map((d) => d.review_count),
        marker: { color: dist.map((d) => palette[d.rating - 1]) },
        hovertemplate: "%{x}: %{y} reviews<extra></extra>",
      },
    ];
  }, [overview.data, colors]);

  if (overview.isLoading) return <Spinner />;
  if (overview.error) return <Notice tone="error" title="Couldn't load the overview">{overview.error.message}</Notice>;
  const o = overview.data!;
  const k = o.kpis;
  const top = board.data?.problems.slice(0, 3) ?? [];
  const toRows = <T,>(items: T[], key: (i: T) => string) =>
    items.map((i) => ({ key: key(i), count: (i as { review_count: number }).review_count }));

  return (
    <div className="flex flex-col gap-6">
      <dl className="grid grid-cols-2 gap-x-8 gap-y-4 border-b border-line pb-6 sm:grid-cols-4">
        <div>
          <dt className="text-sm text-muted">Reviews</dt>
          <dd className="text-2xl font-semibold tabular-nums">{num(k.review_count)}</dd>
          <dd className="text-xs text-muted">
            {shortDate(k.date_from)} to {shortDate(k.date_to)}
          </dd>
        </div>
        <div>
          <dt className="text-sm text-muted">Average rating</dt>
          <dd className="flex items-center gap-2 text-2xl font-semibold tabular-nums">
            {rating(k.avg_rating)} {k.avg_rating != null && <Stars value={k.avg_rating} size="md" />}
          </dd>
        </div>
        <div>
          <dt className="text-sm text-muted">Negative (1–2★)</dt>
          <dd className="text-2xl font-semibold tabular-nums text-neg">{pct(k.negative_share)}</dd>
        </div>
        <div>
          <dt className="text-sm text-muted">Positive (4–5★)</dt>
          <dd className="text-2xl font-semibold tabular-nums text-pos">{pct(k.positive_share)}</dd>
        </div>
      </dl>

      {top.length > 0 && (
        <Panel
          title="Biggest problems"
          actions={
            <Link to="?tab=problems" className="text-sm text-muted underline underline-offset-2 hover:text-ink">
              See all problems
            </Link>
          }
        >
          <ol className="flex flex-col gap-3">
            {top.map((p, i) => (
              <li key={p.theme} className="flex items-baseline gap-3">
                <span className="w-5 shrink-0 text-sm tabular-nums text-muted">{i + 1}</span>
                <span className="highlight font-medium">{p.theme}</span>
                <span className="text-sm text-muted">
                  {plural(p.mentions, "review")}, {pct(p.negative_share)} negative
                </span>
              </li>
            ))}
          </ol>
        </Panel>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Ratings" actions={<ImageLink run={run} chart="rating-distribution" />}>
          <Plot data={ratingData} label="Rating distribution" height={240} />
        </Panel>
        <Panel title="Type of feedback" actions={<ImageLink run={run} chart="feedback-mix" />}>
          <BarList rows={toRows(o.category_distribution, (c) => c.category)} color={colors.ink} labelOf={label} />
        </Panel>
        <Panel title="Where in the journey">
          <BarList rows={toRows(o.journey_distribution, (c) => c.journey_stage)} color={colors.muted} labelOf={label} />
        </Panel>
        <Panel title="How users feel">
          <BarList rows={toRows(o.emotion_distribution, (c) => c.emotion)} color={colors.muted} labelOf={label} />
        </Panel>
      </div>
    </div>
  );
}
