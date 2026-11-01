import { Download, Printer } from "lucide-react";
import { artifactsApi, type Run } from "../../lib/api";
import { Badge, Button } from "../../components/ui";
import { usePins } from "../../components/pins";
import { ArtifactFrame, Evidence } from "./ArtifactFrame";
import { Quote } from "./Problems";

const WHEN = { now: "Now", next: "Next", later: "Later" } as const;

export function ReportTab({ run }: { run: Run }) {
  const pins = usePins();
  return (
    <ArtifactFrame
      run={run}
      kind="report"
      title="UX research report"
      description="A shareable research report written from this analysis: summary, method, key findings with quotes, user needs, opportunities, recommendations and open questions. Download it as Markdown or save it as a PDF."
      generateLabel="Write the report"
    >
      {(artifact) => {
        const r = artifact.content;
        return (
          <div className="flex flex-col gap-6">
            <div className="flex flex-wrap gap-2 print:hidden">
              <a
                href={artifactsApi.markdownUrl(run.id)}
                className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line bg-panel px-3 text-sm font-medium hover:bg-soft"
              >
                <Download className="size-4" aria-hidden /> Download Markdown
              </a>
              <Button size="sm" onClick={() => window.print()}>
                <Printer className="size-4" aria-hidden /> Print or save as PDF
              </Button>
            </div>

            <article className="flex max-w-[72ch] flex-col gap-8 rounded-lg border border-line bg-panel p-8 print:border-0 print:p-0">
              <header className="flex flex-col gap-3">
                <h1 className="font-quote text-3xl font-semibold leading-tight">{r.title}</h1>
                <p className="text-[1.05rem] leading-relaxed">{r.summary}</p>
              </header>

              <section>
                <h2 className="mb-2 font-semibold">Method</h2>
                <p className="text-sm text-muted">{r.method}</p>
              </section>

              <section className="flex flex-col gap-5">
                <h2 className="font-semibold">Key findings</h2>
                {r.key_findings.map((f, i) => (
                  <div key={f.heading} className="flex flex-col gap-2">
                    <h3 className="font-quote text-xl font-semibold">
                      {i + 1}. {f.heading}
                    </h3>
                    <p className="leading-relaxed">{f.detail}</p>
                    <Evidence ids={f.review_ids} reviews={r.reviews} />
                  </div>
                ))}
              </section>

              {r.user_needs.length > 0 && (
                <section>
                  <h2 className="mb-2 font-semibold">User needs</h2>
                  <ul className="list-disc space-y-1 pl-5">{r.user_needs.map((n) => <li key={n}>{n}</li>)}</ul>
                </section>
              )}

              {r.opportunities.length > 0 && (
                <section className="flex flex-col gap-4">
                  <h2 className="font-semibold">Opportunities</h2>
                  {r.opportunities.map((o) => (
                    <div key={o.heading} className="flex flex-col gap-2">
                      <h3 className="font-semibold">{o.heading}</h3>
                      <p className="leading-relaxed">{o.detail}</p>
                      <Evidence ids={o.review_ids} reviews={r.reviews} max={1} />
                    </div>
                  ))}
                </section>
              )}

              {r.recommendations.length > 0 && (
                <section>
                  <h2 className="mb-3 font-semibold">Recommendations</h2>
                  <ul className="flex flex-col gap-3">
                    {r.recommendations.map((rec) => (
                      <li key={rec.heading} className="flex gap-3">
                        <Badge tone={rec.when === "now" ? "neg" : "neutral"}>{WHEN[rec.when]}</Badge>
                        <div>
                          <p className="font-medium">{rec.heading}</p>
                          <p className="text-sm text-muted">{rec.detail}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {r.open_questions.length > 0 && (
                <section>
                  <h2 className="mb-2 font-semibold">Open questions for further research</h2>
                  <ul className="list-disc space-y-1 pl-5">{r.open_questions.map((q) => <li key={q}>{q}</li>)}</ul>
                </section>
              )}

              {pins && pins.pins.length > 0 && (
                <section>
                  <h2 className="mb-1 font-semibold">Pinned evidence</h2>
                  <p className="mb-3 text-sm text-muted">Quotes your team pinned while exploring this analysis.</p>
                  <div className="flex flex-col gap-4">
                    {pins.pins.map((p) => (
                      <div key={p.review_id} className="flex flex-col gap-1.5">
                        <Quote review={p} />
                        {p.note && <p className="ml-4 text-sm text-muted">Note: {p.note}</p>}
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </article>
          </div>
        );
      }}
    </ArtifactFrame>
  );
}
