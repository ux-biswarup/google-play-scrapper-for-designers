import { useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Data } from "plotly.js";
import { RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { api, benchmarksApi, type BenchmarkDetail, type Review, type Run, type RunSummary } from "../lib/api";
import { flag, label, num, pct, relativeTime, shortDate } from "../lib/format";
import { toLLMConfig, useConnection } from "../lib/settings";
import { AppIcon } from "../components/Shell";
import { Plot, useChartColors } from "../components/Plot";
import { Badge, Button, EmptyState, Input, Notice, Panel, Spinner, cx } from "../components/ui";
import { Quote } from "./tabs/Problems";

const runLabel = (run: Run) =>
  `${run.app.title ?? run.app.store_id}${run.country ? ` ${flag(run.country)}` : ""}`;
const periodLabel = (run: Run) =>
  run.date_from || run.date_to ? `${shortDate(run.date_from)} – ${shortDate(run.date_to)}` : shortDate(run.created_at);

// ---- list + builder ----------------------------------------------------------------------------

export function BenchmarksPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const runs = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const benchmarks = useQuery({ queryKey: ["benchmarks"], queryFn: benchmarksApi.list });
  const [picked, setPicked] = useState<string[]>(() => (params.get("add") ? [params.get("add")!] : []));
  const [name, setName] = useState("");
  const eligible = (runs.data ?? []).filter((r) => r.status === "completed" && r.provider !== "legacy");
  const create = useMutation({
    mutationFn: () => benchmarksApi.create(picked, name.trim() || undefined),
    onSuccess: (b) => {
      queryClient.invalidateQueries({ queryKey: ["benchmarks"] });
      navigate(`/benchmark/${b.id}`);
    },
  });
  const toggle = (id: string) =>
    setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length < 4 ? [...p, id] : p));

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Benchmark</h1>
      <p className="mt-2 max-w-prose text-muted">
        Put your app next to competitors, or compare markets or periods. See who's ahead at each step of the journey and
        what users praise elsewhere that you could learn from.
      </p>

      {(benchmarks.data?.length ?? 0) > 0 && (
        <section className="mt-8">
          <h2 className="mb-3 font-semibold">Your comparisons</h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {benchmarks.data!.map((b) => (
              <li key={b.id}>
                <Link to={`/benchmark/${b.id}`} className="flex flex-col gap-2 rounded-lg border border-line bg-panel p-4 hover:border-muted">
                  <span className="font-medium">{b.name}</span>
                  <span className="flex -space-x-1.5">
                    {b.apps.map((a) => (
                      <AppIcon key={a.run_id} src={a.icon_url} title={a.title} size={26} />
                    ))}
                  </span>
                  <span className="text-xs text-muted">Updated {relativeTime(b.updated_at)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="mt-10 flex flex-col gap-4" aria-labelledby="new-benchmark">
        <h2 id="new-benchmark" className="font-semibold">
          New comparison
        </h2>
        <p className="-mt-2 text-sm text-muted">
          Pick 2 to 4 analyses. The first one you pick is treated as yours. Analyze competitors first from{" "}
          <Link to="/new" className="underline underline-offset-2">
            New analysis
          </Link>
          .
        </p>
        {runs.isLoading ? (
          <Spinner />
        ) : eligible.length < 2 ? (
          <EmptyState title="You need at least two finished analyses">Analyze a competitor or another market first.</EmptyState>
        ) : (
          <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-panel">
            {eligible.map((r) => {
              const position = picked.indexOf(r.id);
              return (
                <li key={r.id}>
                  <label className="flex cursor-pointer items-center gap-3 px-4 py-3 hover:bg-soft">
                    <input type="checkbox" checked={position >= 0} onChange={() => toggle(r.id)} className="size-4 accent-current" />
                    <AppIcon src={r.app.icon_url} title={r.app.title ?? r.app.store_id} size={32} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{runLabel(r)}</span>
                      <span className="block text-xs text-muted">
                        {num(r.review_count)} reviews, {periodLabel(r)}, {r.model}
                      </span>
                    </span>
                    {position === 0 && <Badge tone="warn">Yours</Badge>}
                    {position > 0 && <Badge>Compare {position}</Badge>}
                  </label>
                </li>
              );
            })}
          </ul>
        )}
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-full max-w-sm">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name (optional), e.g. Us vs top 3" aria-label="Comparison name" />
          </div>
          <Button variant="primary" disabled={picked.length < 2} busy={create.isPending} onClick={() => create.mutate()}>
            Compare {picked.length >= 2 ? picked.length : ""} analyses
          </Button>
        </div>
        {create.isError && <Notice tone="error" title="Couldn't create the comparison">{create.error.message}</Notice>}
      </section>
    </div>
  );
}

// ---- detail ------------------------------------------------------------------------------------

type Metric = {
  label: string;
  get: (s: RunSummary, run: Run) => number | null;
  format: (v: number) => string;
  better: "high" | "low" | null;
};
const METRICS: Metric[] = [
  { label: "Reviews analyzed", get: (s) => s.reviews, format: (v) => num(v), better: null },
  { label: "Average rating", get: (s) => s.avg_rating, format: (v) => `${v.toFixed(2)}★`, better: "high" },
  { label: "Negative (1–2★)", get: (s) => s.negative_share, format: (v) => pct(v), better: "low" },
  { label: "Positive (4–5★)", get: (s) => s.positive_share, format: (v) => pct(v), better: "high" },
  { label: "Say they're leaving", get: (s) => s.churn_share, format: (v) => pct(v, 1), better: "low" },
  { label: "Store rating", get: (_s, r) => r.app.score, format: (v) => `${v.toFixed(1)}★`, better: "high" },
];

function MetricsTable({ data }: { data: BenchmarkDetail }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[32rem] text-sm">
        <thead>
          <tr>
            <th className="py-2 text-left font-normal text-muted" />
            {data.columns.map((c, i) => (
              <th key={c.run.id} className="px-3 py-2 text-left font-medium">
                <span className="flex items-center gap-2">
                  <AppIcon src={c.run.app.icon_url} title={c.run.app.title ?? ""} size={22} />
                  <span className="truncate">{runLabel(c.run)}</span>
                  {i === 0 && <Badge tone="warn">Yours</Badge>}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {METRICS.map((m) => {
            const values = data.columns.map((c) => m.get(c.summary, c.run));
            const present = values.filter((v): v is number => v != null);
            const best =
              m.better && present.length > 1 ? (m.better === "high" ? Math.max(...present) : Math.min(...present)) : null;
            return (
              <tr key={m.label} className="border-t border-line">
                <th scope="row" className="py-2.5 pr-3 text-left font-normal text-muted">
                  {m.label}
                </th>
                {values.map((v, i) => (
                  <td key={i} className={cx("px-3 py-2.5 tabular-nums", v != null && v === best && "font-semibold text-pos")}>
                    {v == null ? <span className="text-muted">–</span> : m.format(v)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function JourneyHeatmap({ data }: { data: BenchmarkDetail }) {
  const colors = useChartColors();
  const stages = useMemo(() => {
    const all = new Set<string>();
    data.columns.forEach((c) => Object.keys(c.summary.journey).forEach((s) => s !== "other" && all.add(s)));
    return [...all];
  }, [data]);
  const trace = useMemo<Data[]>(
    () => [
      {
        type: "heatmap",
        x: data.columns.map((c) => runLabel(c.run)),
        y: stages.map(label),
        z: stages.map((s) => data.columns.map((c) => (c.summary.journey[s] ? c.summary.journey[s].negative_share * 100 : null))),
        // Plotly accepts a 2-D text grid for heatmaps; its types only describe 1-D.
        text: stages.map((s) =>
          data.columns.map((c) => (c.summary.journey[s] ? `${Math.round(c.summary.journey[s].negative_share * 100)}%` : "")),
        ) as unknown as string[],
        texttemplate: "%{text}",
        textfont: { color: colors.ink },
        colorscale: [
          [0, colors.pos],
          [0.5, colors.hl],
          [1, colors.neg],
        ],
        zmin: 0,
        zmax: 100,
        showscale: false,
        xgap: 3,
        ygap: 3,
        hovertemplate: "%{x}<br>%{y}: %{z:.0f}% negative<extra></extra>",
      },
    ],
    [data, stages, colors],
  );
  if (stages.length === 0) return <p className="text-sm text-muted">No journey tags in these analyses.</p>;
  return <Plot data={trace} label="Share of negative reviews at each journey stage, per app" height={Math.max(220, stages.length * 42 + 60)} layout={{ xaxis: { side: "top", showgrid: false }, yaxis: { showgrid: false } }} />;
}

function MixChart({ data, field, keys }: { data: BenchmarkDetail; field: "feedback_types" | "emotions"; keys: string[] }) {
  const colors = useChartColors();
  const palette: Record<string, string> = {
    bug: colors.neg, ux_friction: colors.warn, complaint: "#b4536a", feature_request: colors.muted, praise: colors.pos,
    question: colors.neu, other: colors.line, frustration: colors.neg, anger: "#b4536a", confusion: colors.warn,
    disappointment: "#c98a5a", neutral: colors.neu, satisfaction: "#7cb87f", delight: colors.pos,
  };
  const traces = useMemo<Data[]>(
    () =>
      keys.map((k) => ({
        type: "bar",
        orientation: "h",
        name: label(k),
        y: data.columns.map((c) => runLabel(c.run)),
        x: data.columns.map((c) => (c.summary[field][k] ?? 0) * 100),
        marker: { color: palette[k] ?? colors.muted },
        hovertemplate: `${label(k)}: %{x:.0f}%<extra>%{y}</extra>`,
      })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [data, field, keys, colors],
  );
  return (
    <Plot
      data={traces}
      label={field === "emotions" ? "Emotion mix per app" : "Type of feedback per app"}
      height={Math.max(200, data.columns.length * 48 + 90)}
      layout={{ barmode: "stack", showlegend: true, legend: { orientation: "h", y: -0.25 }, xaxis: { ticksuffix: "%", range: [0, 100] } }}
    />
  );
}

function Insights({ data }: { data: BenchmarkDetail }) {
  const queryClient = useQueryClient();
  const { connection, ready, modelLabel } = useConnection();
  const colors = useChartColors();
  const generate = useMutation({
    mutationFn: () => benchmarksApi.insights(data.id, toLLMConfig(connection!)),
    onSuccess: (d) => queryClient.setQueryData(["benchmark", data.id], d),
  });
  const ins = data.insights;
  const topicTrace = useMemo<Data[]>(() => {
    if (!ins) return [];
    const topics = [...ins.topics].reverse();
    return [
      {
        type: "heatmap",
        x: data.columns.map((c) => runLabel(c.run)),
        y: topics.map((t) => t.name),
        z: topics.map((t) => t.apps.map((a) => (a.negative_share == null ? null : a.negative_share * 100))),
        text: topics.map((t) => t.apps.map((a) => (a.mentions ? `${pct(a.share, 1)} of reviews` : "not mentioned"))) as unknown as string[],
        texttemplate: "%{text}",
        textfont: { color: colors.ink, size: 11 },
        colorscale: [
          [0, colors.pos],
          [0.5, colors.hl],
          [1, colors.neg],
        ],
        zmin: 0,
        zmax: 100,
        showscale: false,
        xgap: 3,
        ygap: 3,
        hovertemplate: "%{y} in %{x}<br>%{text}, %{z:.0f}% negative<extra></extra>",
      },
    ];
  }, [ins, data, colors]);

  const button = (
    <Button variant={ins ? "secondary" : "primary"} size={ins ? "sm" : "md"} onClick={() => generate.mutate()} busy={generate.isPending} disabled={!ready}>
      {ins ? <RefreshCw className="size-4" aria-hidden /> : <Sparkles className="size-4" aria-hidden />}
      {ins ? "Regenerate" : "Find shared topics and gaps"}
    </Button>
  );
  return (
    <Panel>
      <div className="flex flex-col gap-5">
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="font-semibold">Where you lead and lag</h2>
            <p className="text-xs text-muted">
              {ins
                ? `Written by ${data.model} ${relativeTime(data.updated_at)}. Topic numbers are computed from the reviews.`
                : "The AI lines up each app's themes into shared topics. Leads and lags are computed from the reviews; the AI explains them with quotes."}
            </p>
          </div>
          {(ins || ready) && button}
        </header>
        {!ready && !ins && (
          <p className="text-sm text-muted">
            <Link to="/settings" className="font-medium text-ink underline underline-offset-2">
              Connect an AI model
            </Link>{" "}
            to compare topics.
          </p>
        )}
        {generate.isPending && <Spinner label={`Comparing with ${modelLabel}. This usually takes 15–40 seconds.`} />}
        {generate.isError && <Notice tone="error" title="Couldn't compare">{generate.error.message}</Notice>}
        {ins && !generate.isPending && (
          <>
            <p className="font-quote text-lg leading-snug">{ins.headline}</p>
            <div className="grid gap-5 lg:grid-cols-3">
              {(
                [
                  ["Where you lead", ins.leads, "pos"],
                  ["Where you lag", ins.lags, "neg"],
                  ["Learn from others", ins.opportunities, "warn"],
                ] as const
              ).map(([title, points, tone]) => (
                <section key={title} className="flex flex-col gap-3">
                  <h3 className="font-semibold">
                    <Badge tone={tone}>{title}</Badge>
                  </h3>
                  {points.length === 0 ? (
                    <p className="text-sm text-muted">Nothing clear here.</p>
                  ) : (
                    points.map((p) => (
                      <div key={p.point} className="flex flex-col gap-2 border-t border-line pt-3 first-of-type:border-0 first-of-type:pt-0">
                        {p.subject && (
                          <p className="font-medium">
                            {p.subject.charAt(0).toUpperCase() + p.subject.slice(1)}
                            {p.scope === "journey stage" && <span className="font-normal text-muted"> (journey stage)</span>}
                          </p>
                        )}
                        {p.evidence && <p className="text-xs tabular-nums text-muted">{p.evidence}</p>}
                        <p className="text-sm">{p.point}</p>
                        {p.review_ids.map((rid) => {
                          const r = ins.reviews[rid];
                          return r ? (
                            <div key={rid}>
                              {r.app && <p className="mb-1 text-xs font-medium text-muted">{r.app}</p>}
                              <Quote review={r as unknown as Review} clamp />
                            </div>
                          ) : null;
                        })}
                      </div>
                    ))
                  )}
                </section>
              ))}
            </div>
            {ins.topics.length > 0 && (
              <div>
                <h3 className="mb-1 font-semibold">Shared topics</h3>
                <p className="mb-2 text-xs text-muted">Colour = how negative the reviews are (green good, red bad); text = how often it comes up.</p>
                <Plot data={topicTrace} label="Shared topics across apps" height={Math.max(240, ins.topics.length * 40 + 60)} layout={{ xaxis: { side: "top", showgrid: false }, yaxis: { showgrid: false } }} />
              </div>
            )}
          </>
        )}
      </div>
    </Panel>
  );
}

export function BenchmarkDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const bench = useQuery({ queryKey: ["benchmark", id], queryFn: () => benchmarksApi.get(id) });
  const remove = useMutation({
    mutationFn: () => benchmarksApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["benchmarks"] });
      navigate("/benchmark");
    },
  });
  if (bench.isLoading) return <div className="p-10"><Spinner /></div>;
  if (bench.error || !bench.data)
    return (
      <div className="mx-auto max-w-xl px-6 py-16">
        <Notice tone="error" title="Comparison not found">
          <Link to="/benchmark" className="underline">Back to Benchmark</Link>
        </Notice>
      </div>
    );
  const data = bench.data;
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/benchmark" className="text-sm text-muted hover:text-ink">
            Benchmark
          </Link>
          <h1 className="text-2xl font-semibold tracking-tight">{data.name}</h1>
          <p className="mt-1 text-sm text-muted">
            {data.columns.map((c) => `${runLabel(c.run)} (${num(c.run.review_count)} reviews, ${periodLabel(c.run)})`).join(", ")}
          </p>
        </div>
        <Button size="sm" variant="danger" busy={remove.isPending} onClick={() => window.confirm("Delete this comparison?") && remove.mutate()}>
          <Trash2 className="size-4" aria-hidden /> Delete
        </Button>
      </header>
      <Panel title="At a glance">
        <MetricsTable data={data} />
        <p className="mt-2 text-xs text-muted">Best value in each row is green. Different review counts and periods make small differences unreliable.</p>
      </Panel>
      <Insights data={data} />
      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Where the journey breaks">
          <p className="-mt-1 mb-2 text-xs text-muted">Share of negative reviews at each step. Red cells are where an app loses people.</p>
          <JourneyHeatmap data={data} />
        </Panel>
        <Panel title="Top problems">
          <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${data.columns.length}, minmax(0, 1fr))` }}>
            {data.columns.map((c, i) => (
              <div key={c.run.id} className="min-w-0">
                <p className="mb-2 truncate text-sm font-medium">
                  {runLabel(c.run)} {i === 0 && <Badge tone="warn">Yours</Badge>}
                </p>
                <ol className="flex flex-col gap-1.5 text-sm">
                  {c.summary.top_problems.slice(0, 6).map((p) => (
                    <li key={p.theme}>
                      <Link to={`/runs/${c.run.id}?tab=reviews&theme=${encodeURIComponent(p.theme)}`} className="hover:underline">
                        {p.theme}
                      </Link>{" "}
                      <span className="text-xs text-muted">{pct(p.reach, 1)}</span>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Type of feedback">
          <MixChart data={data} field="feedback_types" keys={["bug", "ux_friction", "complaint", "feature_request", "praise", "question", "other"]} />
        </Panel>
        <Panel title="How users feel">
          <MixChart data={data} field="emotions" keys={["frustration", "anger", "confusion", "disappointment", "neutral", "satisfaction", "delight"]} />
        </Panel>
      </div>
    </div>
  );
}
