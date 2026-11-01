import { useQuery } from "@tanstack/react-query";
import { viewsApi, type Run } from "../../lib/api";
import { label, num, pct, plural } from "../../lib/format";
import { Badge, Notice, Panel, Spinner } from "../../components/ui";
import { Quote } from "./Problems";
import { ReanalyzeNotice, SectionIntro, ThemeLink, TrendBadge } from "./shared";

export function RisksTab({ run }: { run: Run }) {
  const data = useQuery({ queryKey: ["view-risks", run.id], queryFn: () => viewsApi.risks(run.id) });
  if (data.isLoading) return <Spinner />;
  if (data.error) return <Notice tone="error" title="Couldn't load risks">{data.error.message}</Notice>;
  const d = data.data!;
  const leaving = d.churn.left + d.churn.considering;

  return (
    <div className="flex flex-col gap-6">
      <SectionIntro title="Early warnings">
        People who say they left or are about to, the apps they're comparing you with, and money problems. Each is
        counted only when the review says so in its own words.
      </SectionIntro>
      {!d.available && <ReanalyzeNotice run={run} what="people leaving and competitors" />}

      {d.available && (
        <Panel title="People leaving">
          <div className="flex flex-col gap-4">
            <dl className="flex flex-wrap gap-x-10 gap-y-3">
              <div>
                <dt className="text-sm text-muted">Say they left</dt>
                <dd className="text-2xl font-semibold tabular-nums text-neg">{num(d.churn.left)}</dd>
              </div>
              <div>
                <dt className="text-sm text-muted">Say they may leave</dt>
                <dd className="text-2xl font-semibold tabular-nums text-warn">{num(d.churn.considering)}</dd>
              </div>
              <div>
                <dt className="text-sm text-muted">Share of reviews</dt>
                <dd className="text-2xl font-semibold tabular-nums">{pct(d.churn.share, 1)}</dd>
              </div>
              <div className="self-end pb-1">
                <TrendBadge trend={d.churn.trend} />
              </div>
            </dl>
            {leaving === 0 ? (
              <p className="text-sm text-muted">No reviewer says they are leaving.</p>
            ) : (
              <>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <h4 className="mb-1.5 text-sm font-medium">Why they leave</h4>
                    <ul className="flex flex-col gap-1 text-sm">
                      {d.churn.themes.map((t) => (
                        <li key={t.theme} className="flex justify-between gap-3">
                          <span className="highlight">
                            <ThemeLink theme={t.theme} />
                          </span>
                          <span className="tabular-nums text-muted">{t.mentions}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <h4 className="mb-1.5 text-sm font-medium">Who</h4>
                    <ul className="flex flex-wrap gap-1.5">
                      {d.churn.by_user_type.map((u) => (
                        <li key={u.value}>
                          <Badge>
                            {u.value === "unknown" ? "Not stated" : label(u.value)} {u.count}
                          </Badge>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
                <div className="flex flex-col gap-3">
                  {d.churn.quotes.map((q) => (
                    <Quote key={q.review_id} review={q} />
                  ))}
                </div>
              </>
            )}
          </div>
        </Panel>
      )}

      {d.available && (
        <Panel title="Competitors people mention">
          {d.competitors.length === 0 ? (
            <p className="text-sm text-muted">No other apps are named in these reviews.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted">
                  <th className="py-1.5 font-normal">App</th>
                  <th className="py-1.5 font-normal">Mentions</th>
                  <th className="py-1.5 font-normal">Switching</th>
                  <th className="hidden py-1.5 font-normal md:table-cell">In their words</th>
                </tr>
              </thead>
              <tbody>
                {d.competitors.map((c) => (
                  <tr key={c.name} className="border-t border-line align-top">
                    <th scope="row" className="py-2 pr-3 text-left font-medium">{c.name}</th>
                    <td className="py-2 tabular-nums">{c.mentions}</td>
                    <td className="py-2 tabular-nums">{c.switching}</td>
                    <td className="hidden py-2 font-quote md:table-cell">{c.quote && `“${c.quote.content.slice(0, 160)}”`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      )}

      <Panel title="Money problems">
        {d.payments.count === 0 ? (
          <p className="text-sm text-muted">No negative reviews about payments or subscriptions.</p>
        ) : (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-muted">
              {plural(d.payments.count, "negative review")} about payments or subscriptions ({pct(d.payments.share, 1)}),
              mostly about {d.payments.themes.slice(0, 3).map((t) => t.theme).join(", ") || "various issues"}.
            </p>
            {d.payments.quotes.map((q) => (
              <Quote key={q.review_id} review={q} />
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
