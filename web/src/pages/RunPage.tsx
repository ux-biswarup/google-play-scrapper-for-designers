import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ExternalLink, Loader2, MessageSquareText, RotateCcw, Trash2 } from "lucide-react";
import { api, type Run } from "../lib/api";
import { STAGES, compact, flag, num, plural, ratingFilterLabel, shortDate } from "../lib/format";
import { countryName } from "../lib/locales";
import { AppIcon } from "../components/Shell";
import { ChatPanel } from "../components/ChatPanel";
import { Button, Notice, Spinner, cx } from "../components/ui";
import { OverviewTab } from "./tabs/Overview";
import { ProblemsTab } from "./tabs/Problems";
import { TrendsTab } from "./tabs/Trends";
import { ReviewsTab } from "./tabs/Reviews";

const isActive = (run: Run) => run.status === "queued" || run.status === "running";

/** Keep the run in the query cache fresh from the server-sent progress stream. */
function useRunEvents(run: Run | undefined) {
  const queryClient = useQueryClient();
  const id = run?.id;
  const active = run ? isActive(run) : false;
  useEffect(() => {
    if (!id || !active) return;
    const source = new EventSource(api.runEventsUrl(id));
    source.addEventListener("progress", (e) => queryClient.setQueryData(["run", id], JSON.parse((e as MessageEvent).data)));
    source.addEventListener("end", () => {
      source.close();
      queryClient.invalidateQueries({ queryKey: ["runs"] });
    });
    source.onerror = () => source.close(); // the run query keeps polling as a fallback
    return () => source.close();
  }, [id, active, queryClient]);
}

function Progress({ run }: { run: Run }) {
  const cancel = useMutation({ mutationFn: () => api.cancelRun(run.id) });
  const current = STAGES.findIndex((s) => s.id === run.stage);
  const percent = run.progress_total ? Math.round((run.progress_done / run.progress_total) * 100) : 0;

  return (
    <div className="mx-auto max-w-xl px-6 py-16">
      <h2 className="text-xl font-semibold">Analyzing {run.app.title ?? run.app.store_id}</h2>
      <p className="mt-1 text-muted">You can leave this page; the analysis keeps running.</p>
      <ol className="mt-8 flex flex-col gap-4">
        {STAGES.map((stage, index) => {
          const done = index < current;
          const now = index === current;
          return (
            <li key={stage.id} className="flex gap-3">
              <span
                className={cx(
                  "grid size-7 shrink-0 place-items-center rounded-full border text-sm",
                  done && "border-ink bg-ink text-paper",
                  now && "border-ink",
                  !done && !now && "border-line text-muted",
                )}
              >
                {done ? <Check className="size-4" aria-hidden /> : now ? <Loader2 className="size-4 animate-spin" aria-hidden /> : index + 1}
              </span>
              <div className="flex min-w-0 flex-1 flex-col gap-2 pt-0.5">
                <span className={cx(!done && !now && "text-muted", now && "font-medium")}>{stage.label}</span>
                {now && run.progress_total > 0 && (
                  <>
                    <div className="h-1.5 overflow-hidden rounded-full bg-soft" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}>
                      <div className="h-full bg-ink transition-[width] duration-500" style={{ width: `${percent}%` }} />
                    </div>
                    <span className="text-sm text-muted">
                      {num(run.progress_done)} of {plural(run.progress_total, "review")}
                      {run.input_tokens > 0 && `, ${compact(run.input_tokens + run.output_tokens)} tokens so far`}
                    </span>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      <div className="mt-10">
        <Button onClick={() => cancel.mutate()} busy={cancel.isPending} disabled={cancel.isSuccess}>
          {cancel.isSuccess ? "Cancelling…" : "Cancel analysis"}
        </Button>
      </div>
    </div>
  );
}

function Failed({ run }: { run: Run }) {
  const navigate = useNavigate();
  const cancelled = run.status === "cancelled";
  return (
    <div className="mx-auto max-w-xl px-6 py-16">
      <h2 className="text-xl font-semibold">
        {cancelled ? "Analysis cancelled" : `Couldn't analyze ${run.app.title ?? run.app.store_id}`}
      </h2>
      <div className="mt-6">
        {cancelled ? (
          <Notice title="Reviews analyzed before cancelling are saved and reused next time." />
        ) : (
          <Notice tone="error" title="What went wrong">{run.error ?? "Unknown error."}</Notice>
        )}
      </div>
      <div className="mt-6 flex flex-wrap gap-3">
        <Button variant="primary" onClick={() => navigate("/new", { state: { rerun: run } })}>
          <RotateCcw className="size-4" aria-hidden /> Start again
        </Button>
        {!cancelled && (
          <Link to="/settings" className="inline-flex h-10 items-center rounded-md border border-line bg-panel px-4 font-medium hover:bg-soft">
            Check AI connection
          </Link>
        )}
      </div>
    </div>
  );
}

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "problems", label: "Problems" },
  { id: "trends", label: "Trends" },
  { id: "reviews", label: "Reviews" },
] as const;
type TabId = (typeof TABS)[number]["id"];

function Dashboard({ run }: { run: Run }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((t) => t.id === params.get("tab"))?.id ?? "overview") as TabId;
  const remove = useMutation({
    mutationFn: () => api.deleteRun(run.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      navigate("/new");
    },
  });
  const title = run.app.title ?? run.app.store_id;
  const legacy = run.provider === "legacy";
  const [chatOpen, setChatOpen] = useState(() => localStorage.getItem("ri.chat-open") === "1");
  const toggleChat = (open: boolean) => {
    localStorage.setItem("ri.chat-open", open ? "1" : "0");
    setChatOpen(open);
  };

  return (
    <div className="flex h-full min-h-0">
    <div className="min-w-0 flex-1 overflow-y-auto">
    <div className="mx-auto max-w-6xl px-6 py-8">
      <header className="flex flex-wrap items-start gap-4">
        <AppIcon src={run.app.icon_url} title={title} size={56} />
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
            {run.country && (
              <span>
                {flag(run.country)} {countryName(run.country)}
              </span>
            )}
            <span>{plural(run.review_count, "review")}</span>
            <span>{ratingFilterLabel(run.ratings)}</span>
            <span>{legacy ? "Imported from the previous version" : `Analyzed by ${run.model}`}</span>
            <span>{shortDate(run.created_at)}</span>
          </p>
        </div>
        <div className="flex gap-2">
          {run.app.store_url && (
            <a
              href={run.app.store_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-sm text-muted hover:bg-soft hover:text-ink"
            >
              <ExternalLink className="size-4" aria-hidden /> Play Store
            </a>
          )}
          {!chatOpen && (
            <Button size="sm" variant="primary" onClick={() => toggleChat(true)}>
              <MessageSquareText className="size-4" aria-hidden /> Ask AI
            </Button>
          )}
          <Button size="sm" onClick={() => navigate("/new", { state: { rerun: run } })}>
            <RotateCcw className="size-4" aria-hidden /> Run again
          </Button>
          <Button
            size="sm"
            variant="danger"
            busy={remove.isPending}
            onClick={() => window.confirm(`Delete this analysis of ${title}?`) && remove.mutate()}
            aria-label="Delete analysis"
          >
            <Trash2 className="size-4" aria-hidden />
          </Button>
        </div>
      </header>

      {run.message && run.message !== "Analysis complete" && (
        <div className="mt-4">
          <Notice title={run.message} />
        </div>
      )}

      <div role="tablist" aria-label="Analysis views" className="mt-6 flex gap-1 border-b border-line">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            onClick={() => setParams({ tab: t.id })}
            className={cx(
              "-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              tab === t.id ? "border-ink text-ink" : "border-transparent text-muted hover:text-ink",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-6" role="tabpanel">
        {tab === "overview" && <OverviewTab run={run} />}
        {tab === "problems" && <ProblemsTab run={run} />}
        {tab === "trends" && <TrendsTab run={run} />}
        {tab === "reviews" && <ReviewsTab run={run} />}
      </div>
    </div>
    </div>
    {chatOpen && (
      <div className="fixed inset-0 z-40 lg:static lg:z-auto lg:w-[26rem] lg:shrink-0 lg:border-l lg:border-line">
        <ChatPanel run={run} onClose={() => toggleChat(false)} />
      </div>
    )}
    </div>
  );
}

export function RunPage() {
  const { id = "" } = useParams();
  const { data: run, error, isLoading } = useQuery({
    queryKey: ["run", id],
    queryFn: () => api.run(id),
    refetchInterval: (query) => (query.state.data && isActive(query.state.data) ? 3000 : false),
  });
  useRunEvents(run);

  if (isLoading) return <div className="p-10"><Spinner /></div>;
  if (error || !run)
    return (
      <div className="mx-auto max-w-xl px-6 py-16">
        <Notice tone="error" title="Analysis not found">
          It may have been deleted. <Link to="/new" className="underline">Start a new analysis</Link>
        </Notice>
      </div>
    );
  if (isActive(run)) return <Progress run={run} />;
  if (run.status !== "completed") return <Failed run={run} />;
  return <Dashboard run={run} />;
}
