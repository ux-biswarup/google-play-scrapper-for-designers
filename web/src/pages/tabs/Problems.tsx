import { useMemo } from "react";
import { Link, useNavigate } from "react-router";
import type { Data, PlotMouseEvent } from "plotly.js";
import { useQuery } from "@tanstack/react-query";
import { Download, TrendingDown, TrendingUp } from "lucide-react";
import { api, type Review, type Run, type Theme } from "../../lib/api";
import { label, num, pct, plural, rating, shortDate } from "../../lib/format";
import { Badge, EmptyState, Notice, Panel, Spinner, Stars } from "../../components/ui";
import { Plot, useChartColors } from "../../components/Plot";

export function Quote({ review }: { review: Review }) {
  return (
    <figure className="border-l-2 border-line pl-4">
      <blockquote className="font-quote text-[1.05rem] leading-relaxed">{review.content}</blockquote>
      <figcaption className="mt-1 flex flex-wrap items-center gap-x-3 text-xs text-muted">
        <Stars value={review.rating} />
        <span>{shortDate(review.date)}</span>
        {review.app_version !== "unknown" && <span>Version {review.app_version}</span>}
        {review.thumbs_up > 0 && <span>{num(review.thumbs_up)} found this helpful</span>}
      </figcaption>
    </figure>
  );
}

function TrendBadge({ theme }: { theme: Theme }) {
  if (theme.trend === "rising")
    return (
      <Badge tone="neg">
        <TrendingUp className="size-3" aria-hidden /> Rising
      </Badge>
    );
  if (theme.trend === "falling")
    return (
      <Badge tone="pos">
        <TrendingDown className="size-3" aria-hidden /> Falling
      </Badge>
    );
  return null;
}

function ProblemRow({ theme, rank, maxImpact }: { theme: Theme; rank: number; maxImpact: number }) {
  const type = theme.categories[0];
  const stage = theme.journey_stages[0];
  const emotion = theme.emotions[0];
  return (
    <li className="grid gap-4 border-b border-line py-6 md:grid-cols-[2.5rem_1fr]">
      <span className="text-2xl font-semibold tabular-nums text-muted">{rank}</span>
      <div className="flex min-w-0 flex-col gap-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h3 className="text-xl font-semibold">
            <span className="highlight">{theme.theme}</span>
          </h3>
          <TrendBadge theme={theme} />
        </div>

        <div className="flex items-center gap-3">
          <div className="h-1.5 w-40 overflow-hidden rounded-full bg-soft" aria-hidden>
            <div className="h-full bg-neg" style={{ width: `${(theme.impact / maxImpact) * 100}%` }} />
          </div>
          <p className="text-sm text-muted">
            Impact {theme.impact.toFixed(1)}. {plural(theme.mentions, "review")} ({pct(theme.reach, 1)} of all),{" "}
            {pct(theme.negative_share)} negative, average {rating(theme.avg_rating)}★
          </p>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {type && <Badge>{label(type.value)}</Badge>}
          {stage && <Badge>{label(stage.value)}</Badge>}
          {emotion && <Badge>{label(emotion.value)}</Badge>}
          {theme.versions[0] && theme.versions[0].value !== "unknown" && <Badge>Mostly version {theme.versions[0].value}</Badge>}
        </div>

        <div className="mt-1 flex flex-col gap-4">
          {theme.quotes.map((q) => (
            <Quote key={q.review_id} review={q} />
          ))}
        </div>

        <Link
          to={`?tab=reviews&theme=${encodeURIComponent(theme.theme)}`}
          className="self-start text-sm font-medium underline underline-offset-2"
        >
          {theme.mentions === 1 ? "Read the review" : `Read all ${num(theme.mentions)} reviews`}
        </Link>
      </div>
    </li>
  );
}

/** Where each theme sits: how many people mention it vs how negative they are. */
function PriorityMatrix({ themes }: { themes: Theme[] }) {
  const colors = useChartColors();
  const navigate = useNavigate();
  const data = useMemo<Data[]>(() => {
    const labelled = new Set(
      [...themes].filter((t) => t.mentions >= 2).sort((a, b) => b.impact + b.mentions - (a.impact + a.mentions)).slice(0, 10).map((t) => t.theme),
    );
    const color = (t: Theme) => (t.trend === "rising" ? colors.neg : t.trend === "falling" ? colors.pos : colors.muted);
    return [
      {
        type: "scatter",
        mode: "text+markers",
        x: themes.map((t) => t.reach * 100),
        y: themes.map((t) => t.negative_share * 100),
        // Label only the themes that matter most; the rest show their name on hover.
        text: themes.map((t) => (labelled.has(t.theme) ? t.theme : "")),
        hovertext: themes.map((t) => t.theme),
        // Alternate label sides so neighbouring labels don't overlap.
        textposition: themes.map((_, i) => (i % 2 ? "bottom center" : "top center")) as unknown as "top center",
        textfont: { size: 10, color: colors.ink },
        customdata: themes.map((t) => [t.mentions, t.trend]),
        hovertemplate: "<b>%{hovertext}</b><br>%{x:.1f}% of reviews, %{y:.0f}% negative<br>%{customdata[0]} mentions, %{customdata[1]}<extra></extra>",
        marker: {
          size: themes.map((t) => 8 + Math.sqrt(t.mentions) * 4),
          color: themes.map(color),
          opacity: 0.75,
          line: { width: 1, color: colors.ink },
        },
      },
    ];
  }, [themes, colors]);
  const maxReach = Math.max(...themes.map((t) => t.reach * 100), 1);
  const midReach = maxReach / 2;
  const onClick = useMemo(
    () => (e: PlotMouseEvent) => {
      const theme = (e.points[0] as { hovertext?: string } | undefined)?.hovertext;
      if (theme) navigate(`?tab=reviews&theme=${encodeURIComponent(String(theme))}`);
    },
    [navigate],
  );
  return (
    <Panel title="Priority matrix">
      <p className="-mt-1 mb-2 text-sm text-muted">
        Right = many people mention it; up = mostly negative. Top right is where to act first. Red bubbles are growing.
        Click a bubble to read its reviews.
      </p>
      <Plot
        data={data}
        label="Themes by how many reviews mention them and how negative those reviews are"
        height={360}
        onPointClick={onClick}
        layout={{
          xaxis: { title: { text: "Share of reviews mentioning it" }, ticksuffix: "%", range: [0, maxReach * 1.15], zeroline: false },
          yaxis: { title: { text: "Negative reviews" }, ticksuffix: "%", range: [-5, 110], zeroline: false },
          shapes: [
            { type: "line", x0: midReach, x1: midReach, y0: -5, y1: 110, line: { color: colors.line, dash: "dot" } },
            { type: "line", x0: 0, x1: maxReach * 1.15, y0: 50, y1: 50, line: { color: colors.line, dash: "dot" } },
          ],
          annotations: [
            { x: maxReach * 1.12, y: 106, text: "Act first", showarrow: false, xanchor: "right", font: { color: colors.neg, size: 11 } },
            { x: 0.5, y: 106, text: "Watch", showarrow: false, xanchor: "left", font: { color: colors.muted, size: 11 } },
            { x: maxReach * 1.12, y: -2, text: "Protect", showarrow: false, xanchor: "right", font: { color: colors.pos, size: 11 } },
          ],
          margin: { t: 8, r: 8, b: 8, l: 8 },
        }}
      />
    </Panel>
  );
}

export function ProblemsTab({ run }: { run: Run }) {
  const board = useQuery({ queryKey: ["themes", run.id], queryFn: () => api.themes(run.id) });
  if (board.isLoading) return <Spinner />;
  if (board.error) return <Notice tone="error" title="Couldn't load problems">{board.error.message}</Notice>;
  const { problems, strengths, formula } = board.data!;
  const maxImpact = Math.max(...problems.map((p) => p.impact), 1);

  if (problems.length === 0 && strengths.length === 0)
    return (
      <EmptyState title="No themes found in these reviews">
        {run.provider === "legacy"
          ? "This analysis was imported from the previous version, which didn't save themes for this app. Run it again to get problems and strengths."
          : "The reviews may be too short or too few. Try more reviews or all ratings."}
      </EmptyState>
    );

  const allThemes = [...problems, ...strengths.filter((s) => !problems.some((p) => p.theme === s.theme))];

  return (
    <div className="flex flex-col gap-8">
    {allThemes.length >= 3 && <PriorityMatrix themes={allThemes} />}
    <div className="grid gap-10 lg:grid-cols-[1fr_18rem]">
      <section aria-labelledby="problems-heading">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 id="problems-heading" className="text-lg font-semibold">
            Problems, ranked by impact
          </h2>
          <a href={api.chartUrl(run.id, "top-problems")} download className="inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
            <Download className="size-4" aria-hidden /> Image
          </a>
        </div>
        <details className="mt-2 text-sm text-muted">
          <summary className="cursor-pointer select-none hover:text-ink">How impact is calculated</summary>
          <p className="mt-2 max-w-prose">{formula}</p>
        </details>
        {problems.length === 0 ? (
          <p className="mt-6 text-muted">No mostly-negative themes. Users seem happy with what they mention.</p>
        ) : (
          <ol className="mt-2">
            {problems.map((theme, i) => (
              <ProblemRow key={theme.theme} theme={theme} rank={i + 1} maxImpact={maxImpact} />
            ))}
          </ol>
        )}
      </section>

      <aside aria-labelledby="strengths-heading" className="lg:pt-1">
        <h2 id="strengths-heading" className="text-lg font-semibold">
          What users love
        </h2>
        {strengths.length === 0 ? (
          <p className="mt-3 text-sm text-muted">No clearly positive themes in these reviews.</p>
        ) : (
          <ul className="mt-3 flex flex-col divide-y divide-line">
            {strengths.map((s) => (
              <li key={s.theme} className="py-3">
                <Link to={`?tab=reviews&theme=${encodeURIComponent(s.theme)}`} className="font-medium hover:underline">
                  {s.theme}
                </Link>
                <p className="text-sm text-muted">
                  {plural(s.mentions, "review")}, {pct(s.positive_share)} positive
                </p>
                {s.quotes[0] && <p className="mt-1 line-clamp-2 font-quote text-sm">“{s.quotes[0].content}”</p>}
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
    </div>
  );
}
