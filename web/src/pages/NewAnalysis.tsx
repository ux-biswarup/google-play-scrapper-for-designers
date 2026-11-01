import { useDeferredValue, useEffect, useId, useMemo, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Search, SlidersHorizontal, X } from "lucide-react";
import { api, type AppSearchHit, type Run } from "../lib/api";
import { compact, duration, flag, num, shortDate } from "../lib/format";
import { COUNTRIES, INSIGHT_LANGUAGES, LANGUAGES, countryName } from "../lib/locales";
import { toLLMConfig, useConnection } from "../lib/settings";
import { AppIcon } from "../components/Shell";
import { Button, Field, Input, Notice, Segmented, Select, Spinner, Stars, cx } from "../components/ui";

// ---- plan model --------------------------------------------------------------------------------

type Ratings = "all" | "negative" | "critical";
type Period = "any" | "7" | "30" | "90" | "custom";
type Sampling = "spread" | "newest";
type GoalId = "health" | "broken" | "recent" | "deep" | "custom";

type Plan = {
  ratings: Ratings;
  period: Period;
  count: number;
  sampling: Sampling;
};

const RATINGS: Record<Ratings, number[] | null> = { all: null, negative: [1, 2], critical: [1, 2, 3] };

/** Goal-first presets: people think in questions, not parameters. */
const GOALS: { id: Exclude<GoalId, "custom">; title: string; question: string; plan: Plan }[] = [
  {
    id: "health",
    title: "Health check",
    question: "What do users love and hate right now?",
    plan: { ratings: "all", period: "any", count: 300, sampling: "newest" },
  },
  {
    id: "broken",
    title: "What's broken",
    question: "What made people angry this month?",
    plan: { ratings: "negative", period: "30", count: 300, sampling: "spread" },
  },
  {
    id: "recent",
    title: "Recent changes",
    question: "How did the last few weeks go?",
    plan: { ratings: "all", period: "30", count: 500, sampling: "spread" },
  },
  {
    id: "deep",
    title: "Deep dive",
    question: "Everything from the last quarter, for research.",
    plan: { ratings: "all", period: "90", count: 1000, sampling: "spread" },
  },
];

const PERIOD_PHRASE: Record<Exclude<Period, "custom">, string> = {
  any: "",
  "7": "written in the last 7 days",
  "30": "written in the last 30 days",
  "90": "written in the last 90 days",
};
const RATING_PHRASE: Record<Ratings, string> = { all: "", negative: "negative (1–2★) ", critical: "critical (1–3★) " };

const localDay = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 10);
const daysAgo = (n: number) => localDay(new Date(Date.now() - n * 86_400_000));
const looksLikeId = (text: string) => /^[a-z][\w]*(\.[\w]+)+$/i.test(text.trim()) || text.includes("play.google.com");

function ratingsFrom(ratings: number[] | null | undefined): Ratings {
  if (ratings?.join() === "1,2") return "negative";
  if (ratings?.join() === "1,2,3") return "critical";
  return "all";
}

// ---- remembered market (smart defaults) --------------------------------------------------------

const MARKET_KEY = "ri.market";
type Market = { country: string; lang: string; outputLanguage: string };

function defaultMarket(): Market {
  try {
    const saved = JSON.parse(localStorage.getItem(MARKET_KEY) ?? "null") as Market | null;
    if (saved?.country) return saved;
  } catch {
    // ignore
  }
  // First visit: guess from the browser language, e.g. "en-IN" -> India, English.
  const [language, region] = (navigator.language || "en-US").toLowerCase().split("-");
  return {
    country: COUNTRIES.some(([c]) => c === region) ? region : "us",
    lang: LANGUAGES.some(([l]) => l === language) ? language : "en",
    outputLanguage: "English",
  };
}

// ---- small pieces -----------------------------------------------------------------------------

function RecentApps({ onPick }: { onPick: (app: AppSearchHit) => void }) {
  const { data: runs = [] } = useQuery({ queryKey: ["runs"], queryFn: api.runs });
  const apps = useMemo(() => {
    const seen = new Map<string, AppSearchHit>();
    for (const r of runs) {
      if (!seen.has(r.app.store_id) && r.app.title) {
        seen.set(r.app.store_id, { ...r.app });
      }
    }
    return [...seen.values()].slice(0, 5);
  }, [runs]);
  if (apps.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-sm text-muted">Recent:</span>
      {apps.map((a) => (
        <button
          key={a.store_id}
          type="button"
          onClick={() => onPick(a)}
          className="inline-flex items-center gap-2 rounded-full border border-line bg-panel py-1 pl-1 pr-3 text-sm hover:bg-soft"
        >
          <AppIcon src={a.icon_url} title={a.title ?? a.store_id} size={22} />
          {a.title}
        </button>
      ))}
    </div>
  );
}

function GoalTile({ title, question, selected, onSelect }: { title: string; question: string; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onSelect}
      className={cx(
        "flex flex-col gap-1 rounded-lg border p-4 text-left transition-colors",
        selected ? "border-ink bg-panel shadow-[inset_0_0_0_1px_var(--ink)]" : "border-line bg-panel hover:border-muted",
      )}
    >
      <span className="font-semibold">{title}</span>
      <span className="text-sm text-muted">{question}</span>
    </button>
  );
}

function Row({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="grid gap-2 border-t border-line py-4 first:border-t-0 sm:grid-cols-[9rem_1fr] sm:items-start">
      <span className="pt-1.5 text-sm text-muted">{label}</span>
      <div className="flex min-w-0 flex-col items-start gap-2 [&>*]:max-w-full">
        {children}
        {hint && <p className="text-sm text-muted">{hint}</p>}
      </div>
    </div>
  );
}

// ---- page -------------------------------------------------------------------------------------

export function NewAnalysisPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const rerun = (useLocation().state as { rerun?: Run } | null)?.rerun;
  const { connection, provider, ready, modelLabel } = useConnection();
  const ids = { search: useId(), country: useId(), lang: useId(), count: useId(), output: useId(), from: useId(), to: useId() };

  const [text, setText] = useState("");
  const [app, setApp] = useState<AppSearchHit | null>(rerun ? { ...rerun.app } : null);
  const [market, setMarket] = useState<Market>(() =>
    rerun
      ? { country: rerun.country ?? "us", lang: rerun.lang ?? "en", outputLanguage: rerun.output_language }
      : defaultMarket(),
  );
  const [goal, setGoal] = useState<GoalId>(rerun ? "custom" : "health");
  const [plan, setPlan] = useState<Plan>(
    rerun
      ? {
          ratings: ratingsFrom(rerun.ratings),
          period: rerun.date_from || rerun.date_to ? "custom" : "any",
          count: rerun.requested_count,
          sampling: rerun.sampling ?? "spread",
        }
      : GOALS[0].plan,
  );
  const [customFrom, setCustomFrom] = useState(rerun?.date_from ?? daysAgo(30));
  const [customTo, setCustomTo] = useState(rerun?.date_to ?? localDay(new Date()));
  const [adjusting, setAdjusting] = useState(!!rerun);

  useEffect(() => localStorage.setItem(MARKET_KEY, JSON.stringify(market)), [market]);

  const choose = (id: GoalId) => {
    setGoal(id);
    const preset = GOALS.find((g) => g.id === id);
    if (preset) setPlan(preset.plan);
    if (id === "custom") setAdjusting(true);
  };
  const tweak = (patch: Partial<Plan>) => {
    setGoal("custom");
    setPlan((p) => ({ ...p, ...patch }));
  };
  const setMarketField = (patch: Partial<Market>) => setMarket((m) => ({ ...m, ...patch }));

  // App search
  const query = useDeferredValue(text.trim());
  const isId = looksLikeId(query);
  const search = useQuery({
    queryKey: ["search", query, market.country, market.lang],
    queryFn: () => api.searchApps(query, market.country, market.lang),
    enabled: !app && query.length >= 2 && !isId,
    staleTime: 60_000,
  });
  const lookup = useQuery({
    queryKey: ["lookup", query, market.country, market.lang],
    queryFn: () => api.lookupApp(query, market.country, market.lang),
    enabled: !app && isId,
    retry: false,
  });
  const results: AppSearchHit[] = lookup.data ? [lookup.data] : (search.data ?? []);
  const searching = search.isFetching || lookup.isFetching;

  // Period and how many reviews it holds
  const today = localDay(new Date());
  const range =
    plan.period === "any"
      ? null
      : plan.period === "custom"
        ? { from: customFrom, to: customTo }
        : { from: daysAgo(Number(plan.period)), to: today };
  const rangeValid = !range || (!!range.from && !!range.to && range.from <= range.to);
  const reviewWindow = useQuery({
    queryKey: ["review-window", app?.store_id, market.country, market.lang, plan.ratings, range?.from, range?.to],
    queryFn: () =>
      api.reviewWindow({
        app: app!.store_id,
        country: market.country,
        lang: market.lang,
        ratings: RATINGS[plan.ratings],
        date_from: range!.from,
        date_to: range!.to,
      }),
    enabled: !!app && !!range && rangeValid,
    staleTime: 10 * 60_000,
    retry: false,
  });
  const available = range ? reviewWindow.data?.in_range : undefined;
  const maxCount = range ? Math.min(available ?? 0, 2000) : 2000;
  const chosenCount = range ? Math.min(plan.count, maxCount) : Math.max(10, Math.min(plan.count, 2000));
  const counting = !!range && reviewWindow.isFetching;

  const deferredCount = useDeferredValue(chosenCount);
  const estimate = useQuery({
    queryKey: ["estimate", deferredCount],
    queryFn: () => api.estimate(deferredCount),
    staleTime: Infinity,
    enabled: deferredCount > 0,
  });

  const start = useMutation({
    mutationFn: () =>
      api.createRun({
        app: app!.store_id,
        country: market.country,
        lang: market.lang,
        count: chosenCount,
        ratings: RATINGS[plan.ratings],
        output_language: market.outputLanguage,
        llm: toLLMConfig(connection!),
        date_from: range?.from ?? null,
        date_to: range?.to ?? null,
        sampling: range ? plan.sampling : "newest",
      }),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/runs/${run.id}`);
    },
  });

  // The plan, said in one sentence.
  const periodText =
    plan.period === "custom" ? `written ${shortDate(customFrom)} to ${shortDate(customTo)}` : PERIOD_PHRASE[plan.period];
  const howMany = range
    ? available == null
      ? "" // still counting: don't show a number yet
      : chosenCount >= (available ?? 0)
        ? `all ${num(available ?? 0)}`
        : `${num(chosenCount)} of ${num(available ?? 0)}`
    : `the newest ${num(chosenCount)}`;
  const sentence = [
    `${howMany} ${RATING_PHRASE[plan.ratings]}reviews`.trim(),
    periodText,
    range && available != null && chosenCount < (available ?? 0) && plan.sampling === "spread" ? "spread across the period" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const blocked = !app || !ready || (!!range && (!rangeValid || counting || !available));

  return (
    <div className="mx-auto flex min-h-full max-w-3xl flex-col px-6 pt-10">
      <h1 className="text-2xl font-semibold tracking-tight">Analyze an app</h1>
      <p className="mt-2 max-w-prose text-muted">
        See what users struggle with and what they love, with the reviews behind every point.
      </p>
      {!ready && (
        <div className="mt-6">
          <Notice title="Connect an AI model first">
            The analysis uses an AI model to read the reviews.{" "}
            <Link to="/settings" className="font-medium text-ink underline underline-offset-2">
              Connect a model
            </Link>
          </Notice>
        </div>
      )}

      <form
        className="mt-8 flex flex-1 flex-col gap-10"
        onSubmit={(e) => {
          e.preventDefault();
          if (!blocked) start.mutate();
        }}
      >
        {/* 1. Which app? */}
        <section className="flex flex-col gap-3" aria-labelledby="step-app">
          <h2 id="step-app" className="font-semibold">
            Which app?
          </h2>
          {app ? (
            <div className="flex items-center gap-4 rounded-lg border border-line bg-panel p-4">
              <AppIcon src={app.icon_url} title={app.title ?? app.store_id} size={52} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-lg font-semibold">{app.title ?? app.store_id}</p>
                <p className="flex flex-wrap items-center gap-x-3 text-sm text-muted">
                  <span className="truncate">{app.developer}</span>
                  {app.score != null && (
                    <span className="inline-flex items-center gap-1">
                      <Stars value={app.score} /> {app.score.toFixed(1)}
                    </span>
                  )}
                </p>
              </div>
              <Button type="button" variant="ghost" size="sm" onClick={() => setApp(null)}>
                <X className="size-4" aria-hidden /> Change
              </Button>
            </div>
          ) : (
            <>
              <label htmlFor={ids.search} className="sr-only">
                Search Google Play
              </label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-muted" aria-hidden />
                <Input
                  id={ids.search}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Search by name, or paste a Play Store link"
                  className="h-14 pl-12 text-base"
                  autoFocus
                  autoComplete="off"
                />
              </div>
              {!text && <RecentApps onPick={setApp} />}
              {searching && <Spinner label="Searching Google Play" />}
              {lookup.isError && <Notice tone="error" title="App not found">{lookup.error.message}</Notice>}
              {search.isSuccess && !searching && results.length === 0 && (
                <p className="text-sm text-muted">No apps match “{query}”. Try the exact name or paste its link.</p>
              )}
              {results.length > 0 && !searching && (
                <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-panel">
                  {results.map((hit) => (
                    <li key={hit.store_id}>
                      <button type="button" onClick={() => setApp(hit)} className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-soft">
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

        {/* 2. What do you want to learn? (shown once there is an app: one decision at a time) */}
        {app && (
          <section className="flex flex-col gap-3" aria-labelledby="step-goal">
            <h2 id="step-goal" className="font-semibold">
              What do you want to learn?
            </h2>
            <div role="radiogroup" aria-labelledby="step-goal" className="grid gap-3 sm:grid-cols-2">
              {GOALS.map((g) => (
                <GoalTile key={g.id} title={g.title} question={g.question} selected={goal === g.id} onSelect={() => choose(g.id)} />
              ))}
            </div>

            {/* The plan in one sentence, with everything adjustable behind one button. */}
            <div className="mt-2 rounded-lg border border-line bg-panel">
              <div className="flex flex-wrap items-start gap-3 p-4">
                <p className="min-w-0 flex-1 leading-relaxed">
                  Analyze <span className="font-semibold">{sentence}</span> from{" "}
                  <span className="font-semibold">
                    {flag(market.country)} {countryName(market.country)}
                  </span>{" "}
                  in {LANGUAGES.find(([c]) => c === market.lang)?.[1] ?? market.lang}.
                  {counting && <span className="ml-2 inline-flex align-middle"><Spinner label="Counting reviews" /></span>}
                </p>
                <Button type="button" size="sm" onClick={() => setAdjusting((v) => !v)} aria-expanded={adjusting}>
                  <SlidersHorizontal className="size-4" aria-hidden /> {adjusting ? "Done" : "Adjust"}
                  <ChevronDown className={cx("size-4 transition-transform", adjusting && "rotate-180")} aria-hidden />
                </Button>
              </div>
              {range && reviewWindow.data && !counting && (
                <div className="border-t border-line px-4 py-2.5 text-sm">
                  {available === 0 ? (
                    <span className="text-neg">No reviews in this period for this market. Choose a longer period.</span>
                  ) : (
                    <span className="text-muted">
                      {num(available ?? 0)} reviews were written between {shortDate(reviewWindow.data.first_review)} and{" "}
                      {shortDate(reviewWindow.data.last_review)}
                      {(available ?? 0) > 2000 && "; up to 2,000 can be analyzed at once"}.
                    </span>
                  )}
                  {!reviewWindow.data.complete && (
                    <span className="block text-warn">
                      Google Play only reaches back to {shortDate(reviewWindow.data.oldest_reached)} for this app; earlier reviews
                      in the period aren't included.
                    </span>
                  )}
                </div>
              )}
              {reviewWindow.isError && (
                <div className="border-t border-line p-4">
                  <Notice tone="error" title="Couldn't count reviews">{reviewWindow.error.message}</Notice>
                </div>
              )}

              {adjusting && (
                <div className="border-t border-line px-4">
                  <Row label="Period">
                    <div className="overflow-x-auto">
                      <Segmented
                        label="Period"
                        value={plan.period}
                        onChange={(v) => tweak({ period: v })}
                        options={[
                          { value: "any", label: "Any time" },
                          { value: "7", label: "7 days" },
                          { value: "30", label: "30 days" },
                          { value: "90", label: "90 days" },
                          { value: "custom", label: "Custom" },
                        ]}
                      />
                    </div>
                    {plan.period === "custom" && (
                      <div className="flex flex-wrap items-end gap-3">
                        <Field label="From" htmlFor={ids.from}>
                          <Input id={ids.from} type="date" value={customFrom} max={customTo || today} onChange={(e) => setCustomFrom(e.target.value)} className="w-44" />
                        </Field>
                        <Field label="To" htmlFor={ids.to}>
                          <Input id={ids.to} type="date" value={customTo} min={customFrom} max={today} onChange={(e) => setCustomTo(e.target.value)} className="w-44" />
                        </Field>
                      </div>
                    )}
                    {!rangeValid && <p className="text-sm text-neg">The start date must be on or before the end date.</p>}
                  </Row>
                  <Row label="Ratings">
                    <Segmented
                      label="Ratings"
                      value={plan.ratings}
                      onChange={(v) => tweak({ ratings: v })}
                      options={[
                        { value: "all", label: "All" },
                        { value: "negative", label: "1–2★" },
                        { value: "critical", label: "1–3★" },
                      ]}
                    />
                  </Row>
                  <Row
                    label="How many"
                    hint={range ? undefined : "The newest reviews are used."}
                  >
                    <div className="flex w-full items-center gap-3">
                      <input
                        type="range"
                        min={range ? 1 : 50}
                        max={range ? Math.max(1, maxCount) : 2000}
                        step={range ? (maxCount > 300 ? 10 : 1) : 50}
                        value={chosenCount}
                        onChange={(e) => tweak({ count: Number(e.target.value) })}
                        disabled={!!range && !available}
                        className="flex-1 accent-current"
                        aria-label="Number of reviews to analyze"
                      />
                      <Input
                        id={ids.count}
                        type="number"
                        min={1}
                        max={range ? maxCount : 2000}
                        value={chosenCount}
                        onChange={(e) => tweak({ count: Number(e.target.value) || 1 })}
                        disabled={!!range && !available}
                        className="w-24"
                        aria-label="Number of reviews"
                      />
                      {range && available != null && available > 0 && available <= 2000 && chosenCount < available && (
                        <Button type="button" size="sm" onClick={() => tweak({ count: available })}>
                          All {num(available)}
                        </Button>
                      )}
                    </div>
                  </Row>
                  {range && (
                    <Row
                      label="Pick"
                      hint={
                        plan.sampling === "spread"
                          ? "Evenly from start to end, so trends cover the whole period."
                          : "The most recent reviews in the period."
                      }
                    >
                      <Segmented
                        label="How to pick reviews"
                        value={plan.sampling}
                        onChange={(v) => tweak({ sampling: v })}
                        options={[
                          { value: "spread", label: "Spread across the period" },
                          { value: "newest", label: "Newest first" },
                        ]}
                      />
                    </Row>
                  )}
                  <Row label="Market">
                    <div className="grid w-full gap-3 sm:grid-cols-2">
                      <Select aria-label="Country" id={ids.country} value={market.country} onChange={(e) => setMarketField({ country: e.target.value })}>
                        {COUNTRIES.map(([code, name]) => (
                          <option key={code} value={code}>
                            {name}
                          </option>
                        ))}
                      </Select>
                      <Select aria-label="Review language" id={ids.lang} value={market.lang} onChange={(e) => setMarketField({ lang: e.target.value })}>
                        {LANGUAGES.map(([code, name]) => (
                          <option key={code} value={code}>
                            {name} reviews
                          </option>
                        ))}
                      </Select>
                    </div>
                  </Row>
                  <Row label="Write insights in" hint="Theme names and AI summaries use this language.">
                    <Select
                      aria-label="Write insights in"
                      id={ids.output}
                      value={market.outputLanguage}
                      onChange={(e) => setMarketField({ outputLanguage: e.target.value })}
                      className="w-56"
                    >
                      {INSIGHT_LANGUAGES.map((l) => (
                        <option key={l}>{l}</option>
                      ))}
                    </Select>
                  </Row>
                </div>
              )}
            </div>
          </section>
        )}

        {/* 3. Start: always within reach, with cost and time stated up front. */}
        <div className="sticky bottom-0 -mx-6 mt-auto border-t border-line bg-paper/95 px-6 py-4 backdrop-blur">
          {start.isError && (
            <div className="mb-3">
              <Notice tone="error" title="Couldn't start the analysis">{start.error.message}</Notice>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <Button type="submit" variant="primary" disabled={blocked} busy={start.isPending} className="h-11 px-6">
              Start analysis
            </Button>
            <p className="min-w-0 flex-1 text-sm text-muted">
              {!app
                ? "Choose an app to begin."
                : estimate.data && (
                    <>
                      About {duration(estimate.data.seconds)}, roughly {compact(estimate.data.input_tokens + estimate.data.output_tokens)} tokens
                      {ready && ` with ${provider?.name} ${modelLabel}`}. Reviews already analyzed with this model are free.
                    </>
                  )}
            </p>
          </div>
        </div>
      </form>
    </div>
  );
}
