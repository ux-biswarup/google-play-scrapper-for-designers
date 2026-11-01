import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Columns3, Loader2, Menu, Moon, Plug, Plus, Settings2, Sun, X } from "lucide-react";
import { api, type Run } from "../lib/api";
import { flag, plural, relativeTime } from "../lib/format";
import { useConnection, useTheme } from "../lib/settings";
import { cx } from "./ui";

export function AppIcon({ src, title, size = 32 }: { src: string | null | undefined; title: string; size?: number }) {
  return src ? (
    <img src={src} alt="" width={size} height={size} className="shrink-0 rounded-lg border border-line" loading="lazy" />
  ) : (
    <div
      aria-hidden
      style={{ width: size, height: size }}
      className="grid shrink-0 place-items-center rounded-lg bg-soft text-sm font-semibold text-muted"
    >
      {title.charAt(0)}
    </div>
  );
}

function HistoryItem({ run }: { run: Run }) {
  const title = run.app.title ?? run.app.store_id;
  const active = run.status === "queued" || run.status === "running";
  return (
    <NavLink
      to={`/runs/${run.id}`}
      className={({ isActive }) =>
        cx("flex items-center gap-3 rounded-md px-2 py-2 transition-colors", isActive ? "bg-soft" : "hover:bg-soft/60")
      }
    >
      <AppIcon src={run.app.icon_url} title={title} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{title}</p>
        <p className="truncate text-xs text-muted">
          {active ? (
            <span className="inline-flex items-center gap-1">
              <Loader2 className="size-3 animate-spin" aria-hidden /> Analyzing
            </span>
          ) : run.status === "failed" ? (
            <span className="text-neg">Failed</span>
          ) : run.status === "cancelled" ? (
            "Cancelled"
          ) : (
            <>
              {flag(run.country)} {plural(run.review_count, "review")}, {relativeTime(run.created_at)}
            </>
          )}
        </p>
      </div>
    </NavLink>
  );
}

export function Shell() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const { theme, toggle } = useTheme();
  const { ready, provider, modelLabel } = useConnection();
  const { data: runs = [], isLoading } = useQuery({
    queryKey: ["runs"],
    queryFn: api.runs,
    refetchInterval: (query) =>
      query.state.data?.some((r) => r.status === "queued" || r.status === "running") ? 2000 : false,
  });

  // Close the mobile drawer after navigating.
  const [lastPath, setLastPath] = useState(location.pathname);
  if (lastPath !== location.pathname) {
    setLastPath(location.pathname);
    setOpen(false);
  }

  const sidebar = (
    <nav aria-label="Analyses" className="flex h-full flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <NavLink to="/" className="text-lg font-semibold tracking-tight">
          Review Insights
        </NavLink>
        <button className="rounded p-1 text-muted hover:text-ink lg:hidden" onClick={() => setOpen(false)} aria-label="Close menu">
          <X className="size-5" />
        </button>
      </div>
      <NavLink
        to="/new"
        className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-ink px-4 font-medium text-paper hover:opacity-90"
      >
        <Plus className="size-4" aria-hidden /> New analysis
      </NavLink>
      <NavLink
        to="/benchmark"
        className={({ isActive }) =>
          cx("-mt-2 flex items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-soft", isActive && "bg-soft")
        }
      >
        <Columns3 className="size-4 text-muted" aria-hidden />
        Benchmark against competitors
      </NavLink>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <h2 className="mb-1 px-2 text-sm font-medium text-muted">Past analyses</h2>
        {isLoading ? (
          <p className="px-2 text-sm text-muted">Loading…</p>
        ) : runs.length === 0 ? (
          <p className="px-2 text-sm text-muted">Your analyses will appear here.</p>
        ) : (
          <div className="flex flex-col gap-0.5">
            {runs.map((run) => (
              <HistoryItem key={run.id} run={run} />
            ))}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1 border-t border-line pt-3">
        <NavLink
          to="/settings"
          className={({ isActive }) =>
            cx("flex items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-soft", isActive && "bg-soft")
          }
        >
          <Settings2 className="size-4 text-muted" aria-hidden />
          <span className="min-w-0 flex-1 truncate">
            {ready ? (
              <>
                {provider?.name} <span className="text-muted">{modelLabel}</span>
              </>
            ) : (
              <span className="text-warn">Connect an AI model</span>
            )}
          </span>
        </NavLink>
        <NavLink
          to="/connect"
          className={({ isActive }) =>
            cx("flex items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-soft", isActive && "bg-soft")
          }
        >
          <Plug className="size-4 text-muted" aria-hidden />
          Use in Claude, ChatGPT…
        </NavLink>
        <button onClick={toggle} className="flex items-center gap-2 rounded-md px-2 py-2 text-sm text-muted hover:bg-soft hover:text-ink">
          {theme === "dark" ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
      </div>
    </nav>
  );

  return (
    <div className="flex h-full">
      <aside className="hidden w-72 shrink-0 border-r border-line bg-panel lg:block print:hidden">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink/30" onClick={() => setOpen(false)} aria-hidden />
          <aside className="absolute inset-y-0 left-0 w-72 bg-panel shadow-xl">{sidebar}</aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-line bg-panel px-4 py-3 lg:hidden print:hidden">
          <button onClick={() => setOpen(true)} aria-label="Open menu" className="rounded p-1 text-muted hover:text-ink">
            <Menu className="size-5" />
          </button>
          <span className="font-semibold">Review Insights</span>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
