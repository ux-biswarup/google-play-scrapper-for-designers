import { useQuery } from "@tanstack/react-query";
import { viewsApi, type Run } from "../../lib/api";
import { label, num, pct, plural, rating } from "../../lib/format";
import { EmptyState, Notice, Panel, Spinner } from "../../components/ui";
import { Quote } from "./Problems";
import { ReanalyzeNotice, SectionIntro, ShareBar, ThemeLink, TrendBadge } from "./shared";

export function AccessibilityTab({ run }: { run: Run }) {
  const data = useQuery({ queryKey: ["view-accessibility", run.id], queryFn: () => viewsApi.accessibility(run.id) });
  if (data.isLoading) return <Spinner />;
  if (data.error) return <Notice tone="error" title="Couldn't load accessibility">{data.error.message}</Notice>;
  const d = data.data!;
  const intro = (
    <SectionIntro title="Accessibility">
      Reviews about barriers: text size, contrast, screen readers, motion, touch, hearing, cognitive load and physical
      ability. Each need comes with what to check in the design.
    </SectionIntro>
  );
  if (!d.available)
    return (
      <div className="flex flex-col gap-6">
        {intro}
        <ReanalyzeNotice run={run} what="accessibility feedback" />
      </div>
    );
  if (d.count === 0)
    return (
      <div className="flex flex-col gap-6">
        {intro}
        <EmptyState title="No reviewer raises accessibility">
          That doesn't mean there are no barriers: people who can't use an app often leave without reviewing it. Test
          with TalkBack, large text and high contrast to be sure.
        </EmptyState>
      </div>
    );

  return (
    <div className="flex flex-col gap-6">
      {intro}
      <Panel>
        <dl className="flex flex-wrap gap-x-10 gap-y-3">
          <div>
            <dt className="text-sm text-muted">Reviews about accessibility</dt>
            <dd className="text-2xl font-semibold tabular-nums">{num(d.count)}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted">Share of reviews</dt>
            <dd className="text-2xl font-semibold tabular-nums">{pct(d.share, 1)}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted">Their average rating</dt>
            <dd className="text-2xl font-semibold tabular-nums">
              {rating(d.avg_rating)}
              <span className="ml-1.5 text-sm font-normal text-muted">vs {rating(d.overall_avg_rating)} overall</span>
            </dd>
          </div>
          <div className="self-end pb-1">
            <TrendBadge trend={d.trend} />
          </div>
        </dl>
      </Panel>

      {d.areas.length > 0 && (
        <section className="flex flex-col gap-4" aria-labelledby="a11y-needs">
          <h3 id="a11y-needs" className="font-semibold">
            Needs people describe
          </h3>
          <div className="grid gap-4 lg:grid-cols-2">
            {d.areas.map((a) => (
              <Panel key={a.area}>
                <div className="flex flex-col gap-3">
                  <div className="flex items-baseline justify-between gap-3">
                    <h4 className="font-semibold">{a.area}</h4>
                    <span className="text-sm tabular-nums text-muted">
                      {plural(a.count, "review")}, {pct(a.negative_share)} negative
                    </span>
                  </div>
                  <p className="rounded-md bg-soft px-3 py-2 text-sm">
                    <span className="font-medium">Check: </span>
                    {a.check}
                  </p>
                  {a.quotes.map((q) => (
                    <Quote key={q.review_id} review={q} clamp />
                  ))}
                </div>
              </Panel>
            ))}
          </div>
          {d.unmatched > 0 && (
            <p className="text-sm text-muted">
              {plural(d.unmatched, "other accessibility review")} {d.unmatched === 1 ? "doesn't" : "don't"} fit these
              needs; see the quotes below.
            </p>
          )}
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Themes in these reviews">
          <ul className="flex flex-col gap-1.5 text-sm">
            {d.themes.map((t) => (
              <li key={t.theme} className="flex justify-between gap-3">
                <span className="highlight">
                  <ThemeLink theme={t.theme} />
                </span>
                <span className="tabular-nums text-muted">{t.mentions}</span>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Where in the journey">
          <ul className="flex flex-col gap-2.5 text-sm">
            {d.stages.map((s) => (
              <li key={s.value} className="flex flex-col gap-1">
                <span className="flex justify-between gap-3">
                  {label(s.value)} <span className="tabular-nums text-muted">{s.count}</span>
                </span>
                <ShareBar value={s.share} tone="muted" />
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      {d.quotes.length > 0 && (
        <Panel title="In their words">
          <div className="flex flex-col gap-4">
            {d.quotes.map((q) => (
              <Quote key={q.review_id} review={q} />
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}
