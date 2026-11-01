import { useDeferredValue, useEffect, useId, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import { api, type AppSearchHit, type Run } from "../lib/api";
import { compact, duration, num } from "../lib/format";
import { COUNTRIES, INSIGHT_LANGUAGES, LANGUAGES } from "../lib/locales";
import { toLLMConfig, useConnection } from "../lib/settings";
import { AppIcon } from "../components/Shell";
import { Button, Field, Input, Notice, Segmented, Select, Spinner, Stars, cx } from "../components/ui";

type Filter = "all" | "negative" | "critical";
const FILTERS: Record<Filter, number[] | null> = { all: null, negative: [1, 2], critical: [1, 2, 3] };
const looksLikeId = (text: string) => /^[a-z][\w]*(\.[\w]+)+$/i.test(text.trim()) || text.includes("play.google.com");

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
  const ids = { search: useId(), country: useId(), lang: useId(), count: useId(), output: useId() };

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
  const deferredCount = useDeferredValue(count);
  const estimate = useQuery({
    queryKey: ["estimate", deferredCount],
    queryFn: () => api.estimate(deferredCount),
    staleTime: Infinity,
  });

  // Keep the count within the supported range when typed by hand.
  useEffect(() => {
    if (count > 2000) setCount(2000);
  }, [count]);

  const start = useMutation({
    mutationFn: () =>
      api.createRun({
        app: app!.store_id,
        country,
        lang,
        count: Math.max(10, count),
        ratings: FILTERS[filter],
        output_language: outputLanguage,
        llm: toLLMConfig(connection!),
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
          <Field label="Number of reviews" htmlFor={ids.count} hint="The newest reviews are used.">
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={50}
                max={2000}
                step={50}
                value={Math.min(count, 2000)}
                onChange={(e) => setCount(Number(e.target.value))}
                className="flex-1 accent-current"
                aria-label="Number of reviews"
              />
              <Input
                id={ids.count}
                type="number"
                min={10}
                max={2000}
                value={count}
                onChange={(e) => setCount(Number(e.target.value) || 10)}
                className="w-24"
              />
            </div>
          </Field>
          <Field label="Write insights in" htmlFor={ids.output} hint="Theme names use this language.">
            <Select id={ids.output} value={outputLanguage} onChange={(e) => setOutputLanguage(e.target.value)}>
              {INSIGHT_LANGUAGES.map((l) => (
                <option key={l}>{l}</option>
              ))}
            </Select>
          </Field>
          <div className="flex flex-col gap-1.5 sm:col-span-2">
            <span className="text-sm font-medium">Which reviews</span>
            <Segmented
              label="Which reviews"
              value={filter}
              onChange={setFilter}
              options={[
                { value: "all", label: "All ratings" },
                { value: "negative", label: "Negative (1–2★)" },
                { value: "critical", label: "Critical (1–3★)" },
              ]}
            />
            <p className="text-sm text-muted">
              {filter === "all"
                ? "Best for a balanced picture of problems and strengths."
                : "Focuses the analysis on what is going wrong."}
            </p>
          </div>
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
          <div className="flex items-center gap-3">
            <Button type="submit" variant="primary" disabled={!app || !ready} busy={start.isPending}>
              Start analysis
            </Button>
            {!app && <span className="text-sm text-muted">Choose an app first.</span>}
            {app && <span className="text-sm text-muted">{num(Math.max(10, count))} newest reviews</span>}
          </div>
        </section>
      </form>
    </div>
  );
}
