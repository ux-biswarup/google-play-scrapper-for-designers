import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Data, LayoutAxis } from "plotly.js";
import { api, type Comparison, type Grain, type Run } from "../../lib/api";
import { num, pct, plural, rating, shortDate } from "../../lib/format";
import { Plot, useChartColors } from "../../components/Plot";
import { Badge, Field, Notice, Panel, Segmented, Select, Spinner } from "../../components/ui";
import { WhatChangedPanel } from "./WhatChanged";

function pickGrain(run: Run): Grain {
  // A rough guess before data loads; users can switch.
  return run.review_count > 1500 ? "week" : "day";
}

/** Date axis without intra-day ticks: one tick per bucket for short ranges. */
function dateAxis(grain: Grain, points: number): Partial<LayoutAxis> {
  const step = { day: 86_400_000, week: 604_800_000, month: "M1" }[grain];
  return { type: "date", tickformat: grain === "month" ? "%b %Y" : "%b %-d", ...(points <= 14 ? { dtick: step } : {}) };
}

function Delta({ value, invert = false, format }: { value: number | null; invert?: boolean; format: (v: number) => string }) {
  if (value == null) return <span className="text-muted">–</span>;
  const good = invert ? value < 0 : value > 0;
  const tone = value === 0 ? "text-muted" : good ? "text-pos" : "text-neg";
  return <span className={`font-semibold tabular-nums ${tone}`}>{value > 0 ? "+" : ""}{format(value)}</span>;
}

function ComparisonView({ data }: { data: Comparison }) {
  const rows = [
    { label: "Reviews", before: num(data.before.review_count), after: num(data.after.review_count) },
    { label: "Average rating", before: rating(data.before.avg_rating), after: rating(data.after.avg_rating) },
    { label: "Negative share", before: pct(data.before.negative_share), after: pct(data.after.negative_share) },
  ];
  return (
    <div className="flex flex-col gap-5">
      <p className="text-sm text-muted">
        Before {shortDate(data.split_date)} compared with on or after that day.
      </p>
      <table className="w-full max-w-lg text-sm">
        <thead>
          <tr className="text-left text-muted">
            <th className="py-1 font-normal" />
            <th className="py-1 font-normal">Before</th>
            <th className="py-1 font-normal">After</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-t border-line">
              <th scope="row" className="py-2 text-left font-normal text-muted">{r.label}</th>
              <td className="py-2 tabular-nums">{r.before}</td>
              <td className="py-2 tabular-nums">{r.after}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-sm">
        Rating change <Delta value={data.delta_avg_rating} format={(v) => v.toFixed(2)} />, negative share change{" "}
        <Delta value={data.delta_negative_share} invert format={(v) => `${(v * 100).toFixed(1)} pts`} />
      </p>
      <div className="grid gap-6 sm:grid-cols-2">
        <div>
          <h4 className="mb-2 text-sm font-medium">New after the change</h4>
          {data.new_themes.length === 0 ? (
            <p className="text-sm text-muted">No new themes.</p>
          ) : (
            <ul className="flex flex-wrap gap-1.5">
              {data.new_themes.map((t) => (
                <li key={t.theme}><Badge tone="neg">{t.theme} ({t.after_count})</Badge></li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h4 className="mb-2 text-sm font-medium">Mentioned more often</h4>
          {data.rising_themes.length === 0 ? (
            <p className="text-sm text-muted">Nothing grew noticeably.</p>
          ) : (
            <ul className="flex flex-col gap-1 text-sm">
              {data.rising_themes.slice(0, 6).map((t) => (
                <li key={t.theme} className="flex justify-between gap-3">
                  <span>{t.theme}</span>
                  <span className="tabular-nums text-muted">{pct(t.before_share)} to {pct(t.after_share)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

export function TrendsTab({ run }: { run: Run }) {
  const colors = useChartColors();
  const [grain, setGrain] = useState<Grain>(() => pickGrain(run));
  const trends = useQuery({ queryKey: ["trends", run.id, grain], queryFn: () => api.trends(run.id, grain) });
  const [version, setVersion] = useState("");
  const versions = (trends.data?.versions ?? []).filter((v) => v.app_version !== "unknown");
  const pivot = version || versions.at(-1)?.app_version || "";
  const comparison = useQuery({
    queryKey: ["compare", run.id, pivot],
    queryFn: () => api.compare(run.id, "version", pivot),
    enabled: !!pivot && versions.length > 1,
    retry: false,
  });

  const sentimentData = useMemo<Data[]>(() => {
    const s = trends.data?.series ?? [];
    const x = s.map((p) => p.date);
    const counts = s.map((p) => p.review_count);
    const line = (name: string, values: number[], color: string, word: string): Data => ({
      type: "scatter",
      mode: "lines+markers",
      x,
      y: values.map((v) => v * 100),
      customdata: counts,
      name,
      line: { color, width: 2.5 },
      marker: { size: 7 },
      hovertemplate: `%{y:.0f}% ${word} of %{customdata} reviews<extra></extra>`,
    });
    return [
      line("Negative (1–2★)", s.map((p) => p.negative_share), colors.neg, "negative"),
      line("Positive (4–5★)", s.map((p) => p.positive_share), colors.pos, "positive"),
    ];
  }, [trends.data, colors]);

  const spikeData = useMemo<Data[]>(() => {
    const s = trends.data?.spikes.series ?? [];
    return [
      { type: "bar", x: s.map((p) => p.date), y: s.map((p) => p.one_star), name: "1★ reviews", marker: { color: s.map((p) => (p.is_spike ? colors.neg : colors.neu)) }, hovertemplate: "%{y} one-star reviews<extra></extra>" },
      { type: "scatter", mode: "lines", x: s.map((p) => p.date), y: s.map((p) => p.baseline), name: "Usual level", line: { color: colors.ink, dash: "dot", width: 1.5 }, hovertemplate: "Usual level %{y:.1f}<extra></extra>" },
    ];
  }, [trends.data, colors]);

  if (trends.isLoading) return <Spinner />;
  if (trends.error) return <Notice tone="error" title="Couldn't load trends">{trends.error.message}</Notice>;
  const t = trends.data!;
  const fewPoints = t.series.length < 2;

  return (
    <div className="flex flex-col gap-6">
      <WhatChangedPanel run={run} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">
          {plural(t.series.length, grain, `${grain}s`)} of reviews. Short ranges work best per day.
        </p>
        <Segmented
          label="Group by"
          value={grain}
          onChange={setGrain}
          options={[{ value: "day", label: "Day" }, { value: "week", label: "Week" }, { value: "month", label: "Month" }]}
        />
      </div>

      <Panel title="Sentiment over time">
        {fewPoints ? (
          <p className="text-sm text-muted">All reviews fall in one {grain}. Group by a shorter period to see a trend.</p>
        ) : (
          <Plot
            data={sentimentData}
            label="Share of negative and positive reviews over time, with review volume"
            height={300}
            layout={{
              showlegend: true,
              xaxis: dateAxis(grain, t.series.length),
              yaxis: { title: { text: "% of reviews" }, range: [0, 100], ticksuffix: "%" },
            }}
          />
        )}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <Panel title="One-star spikes">
          {fewPoints ? (
            <p className="text-sm text-muted">Needs reviews spread over several {grain}s.</p>
          ) : (
            <Plot
              data={spikeData}
              label="One-star reviews per period against their usual level"
              height={240}
              layout={{ showlegend: true, xaxis: dateAxis(grain, t.spikes.series.length) }}
            />
          )}
          {t.spikes.spikes.length > 0 ? (
            <ul className="mt-4 flex flex-col gap-2 text-sm">
              {t.spikes.spikes.map((s) => (
                <li key={s.date} className="flex flex-wrap gap-x-2">
                  <span className="font-medium">{shortDate(s.date)}</span>
                  <span className="text-muted">
                    {s.one_star} one-star reviews (usually {s.baseline.toFixed(1)})
                    {s.top_themes.length > 0 && `, mostly about ${s.top_themes.join(", ")}`}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            !fewPoints && <p className="mt-3 text-sm text-muted">No unusual spikes in one-star reviews.</p>
          )}
        </Panel>

        <Panel title="Trending this week">
          {t.trending_themes.length === 0 ? (
            <p className="text-sm text-muted">No themes in the last two weeks of reviews.</p>
          ) : (
            <ul className="flex flex-col gap-2 text-sm">
              {t.trending_themes.slice(0, 10).map((th) => (
                <li key={th.theme} className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0 truncate">{th.theme}</span>
                  <span className={`shrink-0 tabular-nums ${th.direction === "up" ? "text-neg" : th.direction === "down" ? "text-pos" : "text-muted"}`}>
                    {th.previous} to {th.current}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <Panel title="Did a release change things?">
        {versions.length < 2 ? (
          <p className="text-sm text-muted">These reviews come from fewer than two app versions, so there is nothing to compare.</p>
        ) : (
          <div className="flex flex-col gap-5">
            <div className="max-w-xs">
              <Field label="Compare from version">
                <Select value={pivot} onChange={(e) => setVersion(e.target.value)}>
                  {[...versions].reverse().map((v) => (
                    <option key={v.app_version} value={v.app_version}>
                      {v.app_version} (first seen {shortDate(v.first_seen)}, {v.review_count} reviews)
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            {comparison.isLoading && <Spinner />}
            {comparison.error && <Notice tone="error" title="Couldn't compare">{comparison.error.message}</Notice>}
            {comparison.data && <ComparisonView data={comparison.data} />}
          </div>
        )}
      </Panel>
    </div>
  );
}
