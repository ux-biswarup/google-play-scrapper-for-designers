import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Data } from "plotly.js";
import { viewsApi, type JourneyStage, type Run } from "../../lib/api";
import { label, pct, plural } from "../../lib/format";
import { Plot, useChartColors } from "../../components/Plot";
import { Badge, EmptyState, Notice, Panel, Spinner, cx } from "../../components/ui";
import { SectionIntro, ShareBar, ThemeLink } from "./shared";

function StageColumn({ stage, worst }: { stage: JourneyStage; worst: boolean }) {
  return (
    <article
      className={cx(
        "flex w-64 shrink-0 flex-col gap-3 rounded-lg border bg-panel p-4",
        worst ? "border-neg" : "border-line",
      )}
      aria-label={label(stage.stage)}
    >
      <header className="flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2">
          <h3 className="font-semibold">{label(stage.stage)}</h3>
          {worst && <Badge tone="neg">Biggest pain</Badge>}
        </div>
        <p className="text-xs text-muted">
          {plural(stage.reviews, "review")} ({pct(stage.share)}), average {stage.avg_rating}★
        </p>
      </header>
      <div className="flex flex-col gap-1">
        <span className="text-xs text-muted">Negative {pct(stage.negative_share)}</span>
        <ShareBar value={stage.negative_share} tone="neg" />
      </div>
      {stage.emotions.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {[...stage.emotions].sort((a, b) => b.count - a.count).slice(0, 2).map((e) => (
            <Badge key={e.value}>
              {label(e.value)} {pct(e.share)}
            </Badge>
          ))}
        </div>
      )}
      {stage.problems.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-medium text-muted">Problems</h4>
          <ul className="flex flex-col gap-1 text-sm">
            {stage.problems.map((p) => (
              <li key={p.theme}>
                <span className="highlight">
                  <ThemeLink theme={p.theme} />
                </span>{" "}
                <span className="text-xs text-muted">{p.mentions}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {stage.praise.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-medium text-muted">Works well</h4>
          <ul className="flex flex-col gap-1 text-sm">
            {stage.praise.map((p) => (
              <li key={p.theme}>
                <ThemeLink theme={p.theme} /> <span className="text-xs text-muted">{p.mentions}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {stage.quote && (
        <blockquote className="mt-auto border-l-2 border-line pl-3 font-quote text-sm leading-relaxed">
          “{stage.quote.content}”
        </blockquote>
      )}
    </article>
  );
}

export function JourneyTab({ run }: { run: Run }) {
  const colors = useChartColors();
  const data = useQuery({ queryKey: ["view-journey", run.id], queryFn: () => viewsApi.journey(run.id) });
  const stages = useMemo(() => (data.data?.stages ?? []).filter((s) => s.stage !== "other"), [data.data]);

  // The classic journey-map "emotional curve": how people feel at each step.
  const curve = useMemo<Data[]>(
    () => [
      {
        type: "scatter",
        mode: "text+lines+markers",
        x: stages.map((s) => label(s.stage)),
        y: stages.map((s) => s.avg_rating),
        text: stages.map((s) => `${s.avg_rating}★`),
        textposition: "top center",
        textfont: { color: colors.ink, size: 11 },
        customdata: stages.map((s) => [s.reviews, Math.round(s.negative_share * 100)]),
        hovertemplate: "%{x}<br>%{y}★ average, %{customdata[0]} reviews, %{customdata[1]}% negative<extra></extra>",
        line: { color: colors.muted, width: 2, shape: "spline" },
        marker: {
          size: stages.map((s) => 10 + Math.sqrt(s.reviews) * 2.5),
          color: stages.map((s) => (s.negative_share >= 0.5 ? colors.neg : s.negative_share >= 0.25 ? colors.warn : colors.pos)),
          line: { width: 0 },
        },
      },
    ],
    [stages, colors],
  );

  if (data.isLoading) return <Spinner />;
  if (data.error) return <Notice tone="error" title="Couldn't load the journey map">{data.error.message}</Notice>;
  if (stages.length === 0) return <EmptyState title="No journey stages found in these reviews" />;

  return (
    <div className="flex flex-col gap-6">
      <SectionIntro title="Where the experience breaks">
        Reviews placed on the user journey. The curve shows the average rating at each step (bigger dot = more reviews,
        red = mostly negative). Start design work where the curve dips and the dots are big.
      </SectionIntro>
      {stages.length >= 2 && (
        <Panel title="Emotional curve">
          <Plot
            data={curve}
            label="Average rating at each journey stage"
            height={260}
            layout={{ yaxis: { range: [0.5, 5.6], dtick: 1, title: { text: "Average rating" } }, margin: { t: 16, r: 16, b: 8, l: 8 } }}
          />
        </Panel>
      )}
      <div className="-mx-1 overflow-x-auto px-1 pb-2">
        <div className="flex gap-3">
          {stages.map((s) => (
            <StageColumn key={s.stage} stage={s} worst={s.stage === data.data!.worst_stage} />
          ))}
        </div>
      </div>
    </div>
  );
}
