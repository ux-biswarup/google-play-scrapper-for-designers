import { useDeferredValue, useEffect, useId, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import { api, type AppSearchHit, type Run } from "../lib/api";
import { compact, duration, num, shortDate } from "../lib/format";
import { COUNTRIES, INSIGHT_LANGUAGES, LANGUAGES } from "../lib/locales";
import { toLLMConfig, useConnection } from "../lib/settings";
import { AppIcon } from "../components/Shell";
import { Button, Field, Input, Notice, Segmented, Select, Spinner, Stars, cx } from "../components/ui";

type Filter = "all" | "negative" | "critical";
const FILTERS: Record<Filter, number[] | null> = { all: null, negative: [1, 2], critical: [1, 2, 3] };
const looksLikeId = (text: string) => /^[a-z][\w]*(\.[\w]+)+$/i.test(text.trim()) || text.includes("play.google.com");

type Period = "any" | "7" | "30" | "90" | "custom";
type Sampling = "spread" | "newest";

/** YYYY-MM-DD in the user's own time zone. */
const localDay = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
const daysAgo = (n: number) => localDay(new Date(Date.now() - n * 86_400_000));

function filterFromRatings(ratings: number[] | null | undefined): Filter {
  if (ratings?.join() === "1,2") return "negative";
  if (ratings?.join() === "1,2,3") return "critical";
  return "all";
}

export function NewAnalysisPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const rerun = (useLocation().state as { rerun?: Run } | null)?.rerun;
  const { connection, provider, ready, modelLabel } = useConnection();

  const [text, setText] = useState("");
  const [app, setApp] = useState<AppSearchHit | null>(rerun ? { ...rerun.app } : null);
  const [country, setCountry] = useState(rerun?.country ?? "us");
  const [lang, setLang] = useState(rerun?.lang ?? "en");
  const [count, setCount] = useState(rerun?.requested_count ?? 300);
  const [filter, setFilter] = useState<Filter>(filterFromRatings(rerun?.ratings));
  const [outputLanguage, setOutputLanguage] = useState(rerun?.output_language ?? "English");
  const [period, setPeriod] = useState<Period>(rerun?.date_from || rerun?.date_to ? "custom" : "any");
  const [customFrom, setCustomFrom] = useState(rerun?.date_from ?? daysAgo(30));
  const [customTo, setCustomTo] = useState(rerun?.date_to ?? localDay(new Date()));
  const [sampling, setSampling] = useState<Sampling>(rerun?.sampling ?? "spread");
  const ids = { search: useId(), country: useId(), lang: useId(), count: useId(), output: useId(), from: useId(), to: useId() };

  const today = localDay(new Date());
  const range =
    period === "any"
      ? null
      : period === "custom"
        ? { from: customFrom, to: customTo }
        : { from: daysAgo(Number(period)), to: today };
  const rangeValid = !range || (!!range.from && !!range.to && range.from <= range.to);
  const reviewWindow = useQuery({
    queryKey: ["review-window", app?.store_id, country, lang, filter, range?.from, range?.to],
    queryFn: () =>
      api.reviewWindow({ app: app!.store_id, country, lang, ratings: FILTERS[filter], date_from: range!.from, date_to: range!.to }),
    enabled: !!app && !!range && rangeValid,
    staleTime: 10 * 60_000,
    retry: false,
  });
  const available = range ? reviewWindow.data?.in_range : undefined;
  const maxCount = range ? Math.min(available ?? 0, 2000) : 2000;
  const chosenCount = range ? Math.min(count, maxCount) : Math.max(10, count);

  const query = useDeferredValue(text.trim());
  const isId = looksLikeId(query);
  const search = useQuery({
    queryKey: ["search", query, country, lang],
    queryFn: () => api.searchApps(query, country, lang),
    enabled: !app && query.length >= 2 && !isId,
    staleTime: 60_000,
  });
  const lookup = useQuery({
    queryKey: ["lookup", query, country, lang],
    queryFn: () => api.lookupApp(query, country, lang),
    enabled: !app && isId,
    retry: false,
  });
  const deferredCount = useDeferredValue(chosenCount);
  const estimate = useQuery({
    queryKey: ["estimate", deferredCount],
    queryFn: () => api.estimate(deferredCount),
    staleTime: Infinity,
  });

  // Keep the count within the supported range when typed by hand.
  useEffect(() => {
    if (count > 2000) setCount(2000);
  }, [count]);

  // Analyze everything when a period has only a few reviews; otherwise keep the user's choice.
  useEffect(() => {
    if (available != null && available > 0 && available < 50) setCount(available);
  }, [available]);

  const start = useMutation({
    mutationFn: () =>
      api.createRun({
        app: app!.store_id,
        country,
        lang,
        count: chosenCount,
        ratings: FILTERS[filter],
        output_language: outputLanguage,
        llm: toLLMConfig(connection!),
        date_from: range?.from ?? null,
        date_to: range?.to ?? null,
        sampling: range ? sampling : "newest",
      }),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/runs/${run.id}`);
    },
  });

  const results: AppSearchHit[] = lookup.data ? [lookup.data] : (search.data ?? []);
  const searching = search.isFetching || lookup.isFetching;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Analyze an app</h1>
      <p className="mt-2 max-w-prose text-muted">
        Find out what users struggle with and what they love. Pick an app from Google Play and the AI groups its reviews
        into problems, requests and praise, with real quotes as evidence.
      </p>

      {!ready && (
        <div className="mt-6">
          <Notice title="Connect an AI model first">
            The analysis needs an AI model to read the reviews.{" "}
            <Link to="/settings" className="font-medium text-ink underline underline-offset-2">
              Connect a model
            </Link>
          </Notice>
        </div>
      )}

      <form
        className="mt-8 flex flex-col gap-8"
        onSubmit={(e) => {
          e.preventDefault();
          if (app && ready) start.mutate();
        }}
      >
        <section className="flex flex-col gap-3">
          <label htmlFor={ids.search} className="text-sm font-medium">
            App
          </label>
          {app ? (
            <div className="flex items-center gap-4 rounded-lg border border-ink bg-panel p-4">
              <AppIcon src={app.icon_url} title={app.title ?? app.store_id} size={56} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-lg font-semibold">{app.title ?? app.store_id}</p>
                <p className="truncate text-sm text-muted">{app.developer}</p>
                {app.score != null && (
                  <p className="mt-1 flex items-center gap-2 text-sm text-muted">
                    <Stars value={app.score} /> {app.score.toFixed(1)}
                  </p>
                )}
              </div>
              <Button type="button" variant="ghost" size="sm" onClick={() => setApp(null)}>
                <X className="size-4" aria-hidden /> Change
              </Button>
            </div>
          ) : (
            <>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
                <Input
                  id={ids.search}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Search Google Play, or paste an app link or ID"
                  className="h-12 pl-10 text-base"
                  autoFocus
                  autoComplete="off"
                />
              </div>
              {searching && <Spinner label="Searching Google Play" />}
              {lookup.isError && <Notice tone="error" title="App not found">{lookup.error.message}</Notice>}
              {search.isSuccess && !searching && results.length === 0 && (
                <p className="text-sm text-muted">No apps match “{query}”. Try the app's exact name or paste its link.</p>
              )}
              {results.length > 0 && !searching && (
                <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-panel">
                  {results.map((hit) => (
                    <li key={hit.store_id}>
                      <button
                        type="button"
                        onClick={() => setApp(hit)}
                        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-soft"
                      >
                        <AppIcon src={hit.icon_url} title={hit.title ?? hit.store_id} size={40} />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate font-medium">{hit.title}</span>
                          <span className="block truncate text-sm text-muted">{hit.developer}</span>
                        </span>
                        {hit.score != null && <span className="text-sm text-muted">{hit.score.toFixed(1)}★</span>}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </section>

        <section className="grid gap-5 sm:grid-cols-2">
          <Field label="Country" htmlFor={ids.country} hint="Reviews from this Play Store market.">
            <Select id={ids.country} value={country} onChange={(e) => setCountry(e.target.value)}>
              {COUNTRIES.map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Review language" htmlFor={ids.lang}>
            <Select id={ids.lang} value={lang} onChange={(e) => setLang(e.target.value)}>
              {LANGUAGES.map(([code, name]) => (
                <option key={code} value={code}>
                  {name}
                </option>
              ))}
            </Select>
          </Field>
        </section>

        <section className="flex flex-col gap-6" aria-labelledby="reviews-heading">
          <h2 id="reviews-heading" className="text-sm font-medium">
            Which reviews
          </h2>
          <div className="flex flex-col gap-2">
            <span className="text-sm text-muted">Period</span>
            <div className="overflow-x-auto">
              <Segmented
                label="Period"
                value={period}
                onChange={setPeriod}
                options={[
                  { value: "any", label: "Any time" },
                  { value: "7", label: "Last 7 days" },
                  { value: "30", label: "Last 30 days" },
                  { value: "90", label: "Last 90 days" },
                  { value: "custom", label: "Custom" },
                ]}
              />
            </div>
            {period === "custom" && (
              <div className="mt-1 flex flex-wrap items-end gap-3">
                <Field label="From" htmlFor={ids.from}>
                  <Input id={ids.from} type="date" value={customFrom} max={customTo || today} onChange={(e) => setCustomFrom(e.target.value)} className="w-44" />
                </Field>
                <Field label="To" htmlFor={ids.to}>
                  <Input id={ids.to} type="date" value={customTo} min={customFrom} max={today} onChange={(e) => setCustomTo(e.target.value)} className="w-44" />
                </Field>
              </div>
            )}
            {!rangeValid && <p className="text-sm text-neg">The start date must be on or before the end date.</p>}
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-sm text-muted">Ratings</span>
            <Segmented
              label="Ratings"
              value={filter}
              onChange={setFilter}
              options={[
                { value: "all", label: "All ratings" },
                { value: "negative", label: "Negative (1–2★)" },
                { value: "critical", label: "Critical (1–3★)" },
              ]}
            />
            <p className="text-sm text-muted">
              {filter === "all" ? "Best for a balanced picture of problems and strengths." : "Focuses the analysis on what is going wrong."}
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <label htmlFor={ids.count} className="text-sm text-muted">
              How many to analyze
            </label>
            {range && !app && <p className="text-sm text-muted">Choose an app to see how many reviews were written in this period.</p>}
            {range && reviewWindow.isFetching && <Spinner label="Counting reviews in this period. Popular apps can take up to a minute." />}
            {range && reviewWindow.isError && <Notice tone="error" title="Couldn't count reviews">{reviewWindow.error.message}</Notice>}
            {range && reviewWindow.data && !reviewWindow.isFetching && (
              <div className="flex flex-col gap-1 text-sm">
                {available === 0 ? (
                  <p className="text-neg">No reviews in this period for this market and language. Try a longer period.</p>
                ) : (
                  <p>
                    <span className="font-semibold tabular-nums">{num(available ?? 0)} reviews</span> written between{" "}
                    {shortDate(reviewWindow.data.first_review)} and {shortDate(reviewWindow.data.last_review)}
                    {(available ?? 0) > 2000 && ". Up to 2,000 can be analyzed at once"}.
                  </p>
                )}
                {!reviewWindow.data.complete && (
                  <p className="text-warn">
                    Google Play only lets us look back to {shortDate(reviewWindow.data.oldest_reached)} for this app, so earlier
                    reviews in your period aren't included. A shorter or more recent period gets full coverage.
                  </p>
                )}
              </div>
            )}
            {(!range || (available ?? 0) > 0) && (
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={range ? 1 : 50}
                  max={range ? Math.max(1, maxCount) : 2000}
                  step={range ? (maxCount > 300 ? 10 : 1) : 50}
                  value={chosenCount}
                  onChange={(e) => setCount(Number(e.target.value))}
                  disabled={!!range && !reviewWindow.data}
                  className="flex-1 accent-current"
                  aria-label="Number of reviews to analyze"
                />
                <Input
                  id={ids.count}
                  type="number"
                  min={1}
                  max={range ? maxCount : 2000}
                  value={chosenCount}
                  onChange={(e) => setCount(Number(e.target.value) || 1)}
                  disabled={!!range && !reviewWindow.data}
                  className="w-24"
                />
                {range && available != null && available > 0 && available <= 2000 && chosenCount < available && (
                  <Button type="button" size="sm" onClick={() => setCount(available)}>
                    Use all {num(available)}
                  </Button>
                )}
              </div>
            )}
            {range ? (
              (available ?? 0) > chosenCount && (
                <div className="mt-1 flex flex-col gap-1.5">
                  <Segmented
                    label="How to pick them"
                    value={sampling}
                    onChange={setSampling}
                    options={[
                      { value: "spread", label: "Spread across the period" },
                      { value: "newest", label: "Newest first" },
                    ]}
                  />
                  <p className="text-sm text-muted">
                    {sampling === "spread"
                      ? "Picks reviews evenly from start to end, so trends and before/after comparisons cover the whole period."
                      : "Uses the most recent reviews in the period."}
                  </p>
                </div>
              )
            ) : (
              <p className="text-sm text-muted">The newest reviews are used. Choose a period to analyze a specific time.</p>
            )}
          </div>
        </section>

        <section className="grid gap-5 sm:grid-cols-2">
          <Field label="Write insights in" htmlFor={ids.output} hint="Theme names use this language.">
            <Select id={ids.output} value={outputLanguage} onChange={(e) => setOutputLanguage(e.target.value)}>
              {INSIGHT_LANGUAGES.map((l) => (
                <option key={l}>{l}</option>
              ))}
            </Select>
          </Field>
        </section>

        <section className="flex flex-col gap-4 border-t border-line pt-6">
          {estimate.data && (
            <p className={cx("text-sm", ready ? "text-ink" : "text-muted")}>
              Takes {duration(estimate.data.seconds)} and roughly {compact(estimate.data.input_tokens + estimate.data.output_tokens)} tokens
              {ready && (
                <>
                  {" "}
                  with {provider?.name} <span className="font-medium">{modelLabel}</span>
                </>
              )}
              . Reviews already analyzed with the same model are reused for free.
            </p>
          )}
          {start.isError && <Notice tone="error" title="Couldn't start the analysis">{start.error.message}</Notice>}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="submit"
              variant="primary"
              disabled={!app || !ready || (!!range && (!rangeValid || reviewWindow.isFetching || !available))}
              busy={start.isPending}
            >
              Start analysis
            </Button>
            {!app && <span className="text-sm text-muted">Choose an app first.</span>}
            {app && !range && <span className="text-sm text-muted">{num(chosenCount)} newest reviews</span>}
            {app && range && available != null && available > 0 && (
              <span className="text-sm text-muted">
                {num(chosenCount)} of {num(available)} reviews from {shortDate(range.from)} to {shortDate(range.to)}
                {chosenCount < available && (sampling === "spread" ? ", spread across the period" : ", newest first")}
              </span>
            )}
          </div>
        </section>
      </form>
    </div>
  );
}
