import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { viewsApi, type Run, type Segment } from "../../lib/api";
import { label, pct, plural } from "../../lib/format";
import { Badge, Notice, Segmented, Spinner, cx } from "../../components/ui";
import { ReanalyzeNotice, SectionIntro, ShareBar, ThemeLink } from "./shared";

const DIMENSIONS = [
  { value: "user_type", label: "User type" },
  { value: "sentiment", label: "Sentiment" },
  { value: "app_version", label: "App version" },
  { value: "upvotes", label: "Helpful votes" },
  { value: "detail", label: "Review detail" },
  { value: "replied", label: "Developer reply" },
];

const HINTS: Record<string, string> = {
  user_type: "Long-time and paying users matter most for retention and revenue; new users show onboarding problems.",
  sentiment: "What unhappy reviewers talk about that happy ones don't is often the fastest win.",
  app_version: "Themes concentrated in one version point to a regression in that release.",
  upvotes: "Reviews many others found helpful represent shared pain, not one-off complaints.",
  detail: "Detailed reviews are the richest research material; one-liners show gut reactions.",
  replied: "Shows which problems your team already answers and which go unanswered.",
};

function segmentName(by: string, value: string) {
  if (by === "user_type" && value === "unknown") return "Not stated";
  if (by === "app_version") return value === "other" ? "Other versions" : `Version ${value}`;
  return label(value);
}

function SegmentCard({ segment, by }: { segment: Segment; by: string }) {
  return (
    <article className="flex flex-col gap-3 rounded-lg border border-line bg-panel p-4">
      <header>
        <h3 className="font-semibold">{segmentName(by, segment.value)}</h3>
        <p className="text-xs text-muted">
          {plural(segment.reviews, "review")} ({pct(segment.share)}), average {segment.avg_rating}★
        </p>
      </header>
      <div className="flex flex-col gap-1">
        <span className="text-xs text-muted">Negative {pct(segment.negative_share)}</span>
        <ShareBar value={segment.negative_share} tone="neg" />
      </div>
      {segment.distinctive_themes.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-medium text-muted">Talk about more than others</h4>
          <ul className="flex flex-col gap-1 text-sm">
            {segment.distinctive_themes.map((t) => (
              <li key={t.theme}>
                <span className="highlight">
                  <ThemeLink theme={t.theme} />
                </span>{" "}
                <span className="text-xs text-muted">{t.lift.toFixed(1)}× as often</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {segment.top_themes.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-medium text-muted">Most mentioned</h4>
          <ul className="flex flex-wrap gap-1">
            {segment.top_themes.slice(0, 4).map((t) => (
              <li key={t.theme}>
                <Badge>
                  {t.theme} {pct(t.share)}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
      {segment.quote && (
        <blockquote className="mt-auto border-l-2 border-line pl-3 font-quote text-sm leading-relaxed line-clamp-4">
          “{segment.quote.content}”
        </blockquote>
      )}
    </article>
  );
}

export function SegmentsTab({ run }: { run: Run }) {
  const [by, setBy] = useState(run.tag_version >= 2 ? "user_type" : "sentiment");
  const data = useQuery({
    queryKey: ["view-segments", run.id, by],
    queryFn: () => viewsApi.segments(run.id, by),
    placeholderData: keepPreviousData,
  });
  const d = data.data;

  return (
    <div className="flex flex-col gap-6">
      <SectionIntro title="Compare groups of reviewers">{HINTS[by]}</SectionIntro>
      <div className="overflow-x-auto">
        <Segmented label="Group by" value={by} onChange={setBy} options={DIMENSIONS} />
      </div>
      {data.isLoading && <Spinner />}
      {data.error && <Notice tone="error" title="Couldn't load segments">{data.error.message}</Notice>}
      {d?.needs_reanalysis ? (
        <ReanalyzeNotice run={run} what="user types" />
      ) : (
        d && (
          <div className={cx("grid gap-3 sm:grid-cols-2 xl:grid-cols-3", data.isPlaceholderData && "opacity-60")}>
            {d.segments.map((s) => (
              <SegmentCard key={s.value} segment={s} by={d.by} />
            ))}
          </div>
        )
      )}
    </div>
  );
}
