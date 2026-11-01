import { useDeferredValue, useId, useState } from "react";
import { useSearchParams } from "react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import { api, type Review, type ReviewQuery, type Run } from "../../lib/api";
import { label, num, shortDate } from "../../lib/format";
import { PinButton } from "../../components/pins";
import { Badge, Button, EmptyState, Input, Notice, Select, Spinner, Stars, cx } from "../../components/ui";

const PAGE_SIZE = 20;
const FILTER_KEYS = ["theme", "category", "journey_stage", "emotion", "app_version"] as const;

function ReviewItem({ review }: { review: Review }) {
  return (
    <li className="flex flex-col gap-2 border-b border-line py-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        <Stars value={review.rating} />
        <span>{shortDate(review.date)}</span>
        {review.app_version !== "unknown" && <span>Version {review.app_version}</span>}
        {review.thumbs_up > 0 && <span>{num(review.thumbs_up)} found this helpful</span>}
        <PinButton reviewId={review.review_id} />
      </div>
      <p className="max-w-[72ch] font-quote text-[1.05rem] leading-relaxed">{review.content || <span className="text-muted">No text, rating only.</span>}</p>
      <div className="flex flex-wrap gap-1.5">
        {review.category && <Badge>{label(review.category)}</Badge>}
        {review.journey_stage && review.journey_stage !== "other" && <Badge>{label(review.journey_stage)}</Badge>}
        {review.emotion && review.emotion !== "neutral" && <Badge>{label(review.emotion)}</Badge>}
        {review.themes.map((t) => (
          <Badge key={t} tone="warn">{t}</Badge>
        ))}
      </div>
      {review.reply && (
        <div className="mt-1 max-w-[72ch] rounded-md bg-soft px-3 py-2 text-sm">
          <span className="font-medium">Developer reply: </span>
          <span className="text-muted">{review.reply}</span>
        </div>
      )}
    </li>
  );
}

export function ReviewsTab({ run }: { run: Run }) {
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(params.get("q") ?? "");
  const q = useDeferredValue(text.trim());
  const searchId = useId();
  const ratings = params.getAll("rating").map(Number);
  const page = Number(params.get("page") ?? 1);
  const sort = params.get("sort") ?? "newest";

  const filters: ReviewQuery = {
    q: q || undefined,
    rating: ratings.length ? ratings : undefined,
    sort,
    page,
    page_size: PAGE_SIZE,
    ...Object.fromEntries(FILTER_KEYS.map((k) => [k, params.get(k) ?? undefined])),
  };

  const overview = useQuery({ queryKey: ["overview", run.id], queryFn: () => api.overview(run.id) });
  const board = useQuery({ queryKey: ["themes", run.id], queryFn: () => api.themes(run.id) });
  const trends = useQuery({ queryKey: ["trends", run.id, "day"], queryFn: () => api.trends(run.id, "day") });
  const reviews = useQuery({
    queryKey: ["reviews", run.id, filters],
    queryFn: () => api.reviews(run.id, filters),
    placeholderData: keepPreviousData,
  });

  const setParam = (key: string, value: string | string[] | null) => {
    const next = new URLSearchParams(params);
    next.delete(key);
    next.delete("page");
    if (Array.isArray(value)) value.forEach((v) => next.append(key, v));
    else if (value) next.set(key, value);
    setParams(next);
  };
  const toggleRating = (r: number) =>
    setParam("rating", (ratings.includes(r) ? ratings.filter((x) => x !== r) : [...ratings, r]).map(String));
  const activeFilters = FILTER_KEYS.filter((k) => params.get(k)).length + (ratings.length ? 1 : 0) + (q ? 1 : 0);

  const themes = [...(board.data?.problems ?? []), ...(board.data?.strengths ?? [])].map((t) => t.theme).sort();
  const o = overview.data;
  const options: Record<(typeof FILTER_KEYS)[number], { label: string; values: string[] }> = {
    theme: { label: "All themes", values: [...new Set(themes)] },
    category: { label: "All feedback types", values: o?.category_distribution.map((c) => c.category) ?? [] },
    journey_stage: { label: "All journey stages", values: o?.journey_distribution.map((c) => c.journey_stage) ?? [] },
    emotion: { label: "All emotions", values: o?.emotion_distribution.map((c) => c.emotion) ?? [] },
    app_version: { label: "All versions", values: (trends.data?.versions ?? []).map((v) => v.app_version).reverse() },
  };

  const total = reviews.data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="grid gap-8 lg:grid-cols-[15rem_1fr]">
      <aside className="flex flex-col gap-4" aria-label="Filters">
        <div className="relative">
          <label htmlFor={searchId} className="sr-only">Search reviews</label>
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
          <Input
            id={searchId}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setParam("q", e.target.value.trim() || null);
            }}
            placeholder="Search text"
            className="pl-9"
          />
        </div>
        <fieldset>
          <legend className="mb-1.5 text-sm font-medium">Rating</legend>
          <div className="flex gap-1">
            {[1, 2, 3, 4, 5].map((r) => (
              <button
                key={r}
                type="button"
                aria-pressed={ratings.includes(r)}
                onClick={() => toggleRating(r)}
                className={cx(
                  "h-8 flex-1 rounded border text-sm tabular-nums",
                  ratings.includes(r) ? "border-ink bg-ink text-paper" : "border-line bg-panel text-muted hover:text-ink",
                )}
              >
                {r}★
              </button>
            ))}
          </div>
        </fieldset>
        {FILTER_KEYS.map((key) => (
          <Select key={key} aria-label={options[key].label} value={params.get(key) ?? ""} onChange={(e) => setParam(key, e.target.value || null)}>
            <option value="">{options[key].label}</option>
            {options[key].values.map((v) => (
              <option key={v} value={v}>
                {key === "theme" || key === "app_version" ? v : label(v)}
              </option>
            ))}
          </Select>
        ))}
        {activeFilters > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setText("");
              setParams({ tab: "reviews" });
            }}
          >
            <X className="size-4" aria-hidden /> Clear filters
          </Button>
        )}
      </aside>

      <section aria-live="polite">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
          <p className="text-sm text-muted">
            {reviews.isFetching && !reviews.data ? "Loading…" : `${num(total)} of ${num(run.review_count)} reviews`}
          </p>
          <Select aria-label="Sort" value={sort} onChange={(e) => setParam("sort", e.target.value)} className="h-8 w-56 text-sm">
            <option value="newest">Newest first</option>
            <option value="oldest">Oldest first</option>
            <option value="rating_asc">Lowest rating first</option>
            <option value="rating_desc">Highest rating first</option>
            <option value="most_helpful">Most helpful first</option>
          </Select>
        </div>

        {reviews.error && <div className="mt-4"><Notice tone="error" title="Couldn't load reviews">{reviews.error.message}</Notice></div>}
        {reviews.isLoading && <div className="mt-4"><Spinner /></div>}
        {reviews.data && total === 0 && (
          <div className="mt-6">
            <EmptyState title="No reviews match these filters">Remove a filter or search for a different word.</EmptyState>
          </div>
        )}
        <ul className={cx(reviews.isPlaceholderData && "opacity-60")}>
          {reviews.data?.items.map((r) => <ReviewItem key={r.review_id} review={r} />)}
        </ul>

        {pages > 1 && (
          <nav className="mt-6 flex items-center gap-3" aria-label="Pages">
            <Button size="sm" disabled={page <= 1} onClick={() => setParams((p) => { p.set("page", String(page - 1)); return p; })}>
              Previous
            </Button>
            <span className="text-sm text-muted">Page {page} of {pages}</span>
            <Button size="sm" disabled={page >= pages} onClick={() => setParams((p) => { p.set("page", String(page + 1)); return p; })}>
              Next
            </Button>
          </nav>
        )}
      </section>
    </div>
  );
}
