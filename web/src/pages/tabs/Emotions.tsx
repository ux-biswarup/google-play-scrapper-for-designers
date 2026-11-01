import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Data } from "plotly.js";
import { viewsApi, type Run } from "../../lib/api";
import { label, pct } from "../../lib/format";
import { Plot, useChartColors } from "../../components/Plot";
import { EmptyState, Notice, Panel, Spinner } from "../../components/ui";
import { SectionIntro, ShareBar } from "./shared";

const ORDER = ["frustration", "anger", "confusion", "disappointment", "neutral", "satisfaction", "delight"];
const NEGATIVE = new Set(["frustration", "anger", "confusion", "disappointment"]);

export function EmotionsTab({ run }: { run: Run }) {
  const colors = useChartColors();
  const data = useQuery({ queryKey: ["view-emotions", run.id], queryFn: () => viewsApi.emotions(run.id) });
  const d = data.data;

  const emotionColor = (e: string) =>
    ({ frustration: colors.neg, anger: colors.neg, confusion: colors.warn, disappointment: colors.warn, delight: colors.pos, satisfaction: colors.pos })[e] ??
    colors.neu;

  const heatmap = useMemo<Data[]>(() => {
    if (!d) return [];
    const rows = [...d.matrix].reverse();
    return [
      {
        type: "heatmap",
        x: ORDER.map(label),
        y: rows.map((r) => r.theme),
        z: rows.map((r) => ORDER.map((e) => r.counts[e] ?? 0)),
        colorscale: [
          [0, "rgba(0,0,0,0)"],
          [1, colors.ink],
        ],
        showscale: false,
        xgap: 2,
        ygap: 2,
        hovertemplate: "%{y}<br>%{x}: %{z} reviews<extra></extra>",
      },
    ];
  }, [d, colors]);

  const series = useMemo<Data[]>(() => {
    if (!d) return [];
    return ["frustration", "anger", "confusion", "delight"].map((e) => ({
      type: "scatter",
      mode: "lines+markers",
      name: label(e),
      x: d.series.map((p) => p.date),
      y: d.series.map((p) => Number(p[e] ?? 0) * 100),
      line: { color: emotionColor(e), width: 2, dash: e === "confusion" ? "dot" : e === "anger" ? "dash" : "solid" },
      hovertemplate: `%{y:.0f}% ${label(e).toLowerCase()}<extra></extra>`,
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d, colors]);

  if (data.isLoading) return <Spinner />;
  if (data.error) return <Notice tone="error" title="Couldn't load emotions">{data.error.message}</Notice>;
  if (!d || d.distribution.length === 0) return <EmptyState title="No emotions found in these reviews" />;

  const byValue = Object.fromEntries(d.distribution.map((x) => [x.value, x]));
  return (
    <div className="flex flex-col gap-6">
      <SectionIntro title="How people feel, and what it means">
        Each feeling points to a different kind of decision. Confusion is usually a design fix; anger usually needs a
        product or policy decision.
      </SectionIntro>
      <Panel>
        <ul className="flex flex-col divide-y divide-line">
          {ORDER.filter((e) => byValue[e]).map((e) => (
            <li key={e} className="grid gap-2 py-3 sm:grid-cols-[9rem_6rem_1fr] sm:items-center">
              <span className="font-medium">{label(e)}</span>
              <div className="flex items-center gap-2">
                <span className="w-10 text-sm tabular-nums">{pct(byValue[e].share)}</span>
                <ShareBar value={byValue[e].share} tone={NEGATIVE.has(e) ? "neg" : e === "neutral" ? "muted" : "pos"} />
              </div>
              <div className="text-sm text-muted">
                {d.meaning[e]}
                {d.quotes[e]?.[0] && <p className="mt-1 line-clamp-2 font-quote text-ink">“{d.quotes[e][0].content}”</p>}
              </div>
            </li>
          ))}
        </ul>
      </Panel>
      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Which themes trigger which feelings">
          <Plot data={heatmap} label="Reviews per theme and emotion" height={Math.max(260, d.matrix.length * 28 + 60)} layout={{ xaxis: { side: "top" } }} />
        </Panel>
        <Panel title="Feelings over time">
          {d.series.length < 2 ? (
            <p className="text-sm text-muted">Needs reviews from more than one {d.grain}.</p>
          ) : (
            <Plot data={series} label="Share of key emotions over time" height={280} layout={{ showlegend: true, yaxis: { ticksuffix: "%" } }} />
          )}
        </Panel>
      </div>
    </div>
  );
}
