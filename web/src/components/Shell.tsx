import { useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Columns3, Loader2, Menu, Moon, PanelLeftClose, PanelLeftOpen, Plug, Plus, Search, Settings2, Sun, X } from "lucide-react";
import { api, type Run } from "../lib/api";
import { flag, plural, relativeTime } from "../lib/format";
import { highlightParts, searchRuns } from "../lib/runSearch";
import { useConnection, useTheme } from "../lib/settings";
import { AuthorAvatar } from "../pages/About";
import { Logo } from "./Logo";
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

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
const SHORTCUT = isMac ? "⌘\\" : "Ctrl+\\";
const STORAGE_KEY = "ri.sidebar";

/** Collapsed state of the desktop sidebar, remembered across visits, toggled with ⌘\ or Ctrl+\. */
function useRail(): [boolean, () => void] {
  const [rail, setRail] = useState(() => localStorage.getItem(STORAGE_KEY) === "rail");
  const toggle = useCallback(() => {
    setRail((r) => {
      localStorage.setItem(STORAGE_KEY, r ? "full" : "rail");
      return !r;
    });
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "\\" && (isMac ? e.metaKey : e.ctrlKey) && !e.altKey && !e.shiftKey) {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);
  return [rail, toggle];
}

/**
 * Label shown to the right of a rail icon on hover and keyboard focus. Rendered in a portal so the scrolling
 * history list doesn't clip it. Purely visual: the hidden label inside each row is its accessible name.
 */
function RailTip({ on, label, detail, children }: { on: boolean; label: string; detail?: ReactNode; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [at, setAt] = useState<{ top: number; left: number } | null>(null);
  const show = () => {
    if (!on) return;
    const box = ref.current?.getBoundingClientRect();
    if (box) setAt({ top: box.top + box.height / 2, left: box.right + 10 });
  };
  const hide = () => setAt(null);
  return (
    <div ref={ref} onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>
      {children}
      {at &&
        on &&
        createPortal(
          <div
            role="presentation"
            style={{ top: at.top, left: at.left }}
            className="pointer-events-none fixed z-50 max-w-64 -translate-y-1/2 rounded-md bg-ink px-2.5 py-1.5 text-sm text-paper shadow-lg"
          >
            <p className="font-medium">{label}</p>
            {detail && <p className="text-xs opacity-75">{detail}</p>}
          </div>,
          document.body,
        )}
    </div>
  );
}

// Every row has the same anatomy in both states: a fixed 40px icon slot, then a label. Collapsing only narrows
// the sidebar and hides the labels, so icons never move.
const row = "flex w-full items-center rounded-md text-sm transition-colors";
const slot = "relative grid w-10 shrink-0 place-items-center";
const navRow = (active: boolean) => cx(row, "h-10", active ? "bg-soft text-ink" : "text-ink hover:bg-soft");

function Label({ hidden, children, className }: { hidden: boolean; children: ReactNode; className?: string }) {
  return <span className={cx(hidden ? "sr-only" : "min-w-0 flex-1 truncate pr-2 text-left whitespace-nowrap", className)}>{children}</span>;
}

function runStatus(run: Run): string {
  if (run.status === "queued" || run.status === "running") return "Analyzing";
  if (run.status === "failed") return "Failed";
  if (run.status === "cancelled") return "Cancelled";
  return `${flag(run.country)} ${plural(run.review_count, "review")}, ${relativeTime(run.created_at)}`;
}

function Highlight({ text, query }: { text: string; query: string }) {
  return (
    <>
      {highlightParts(text, query).map((p, i) =>
        p.match ? (
          <mark key={i} className="bg-transparent font-semibold text-ink underline decoration-ink/40 decoration-2 underline-offset-2">
            {p.text}
          </mark>
        ) : (
          p.text
        ),
      )}
    </>
  );
}

function HistoryItem({ run, query, rail }: { run: Run; query: string; rail: boolean }) {
  const title = run.app.title ?? run.app.store_id;
  const active = run.status === "queued" || run.status === "running";
  return (
    <RailTip on={rail} label={title} detail={runStatus(run)}>
      <NavLink
        to={`/runs/${run.id}`}
        className={({ isActive }) => cx(row, "h-12", isActive ? "bg-soft" : "hover:bg-soft/60")}
      >
        <span className={slot}>
          <AppIcon src={run.app.icon_url} title={title} size={30} />
          {active && (
            <span className="absolute -right-0.5 -bottom-1.5 grid size-4 place-items-center rounded-full bg-panel">
              <Loader2 className="size-3 animate-spin text-ink" aria-hidden />
            </span>
          )}
          {run.status === "failed" && (
            <span className="absolute top-0 right-0.5 size-2.5 rounded-full border-2 border-panel bg-neg" aria-hidden />
          )}
        </span>
        <span className={rail ? "sr-only" : "min-w-0 flex-1 pr-2"}>
          <span className="block truncate font-medium">
            <Highlight text={title} query={query} />
          </span>
          <span className={cx("block truncate text-xs", run.status === "failed" ? "text-neg" : "text-muted")}>
            {active ? (
              <span className="inline-flex items-center gap-1">
                <Loader2 className="size-3 animate-spin" aria-hidden /> Analyzing
              </span>
            ) : (
              runStatus(run)
            )}
          </span>
        </span>
      </NavLink>
    </RailTip>
  );
}

function HistorySearch({
  id,
  value,
  onChange,
  onSubmit,
  inputRef,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  inputRef: RefObject<HTMLInputElement | null>;
}) {
  return (
    <div role="search" className="relative">
      <label htmlFor={id} className="sr-only">
        Search analyses
      </label>
      <span className="pointer-events-none absolute inset-y-0 left-0 grid w-10 place-items-center text-muted" aria-hidden>
        <Search className="size-4" />
      </span>
      <input
        ref={inputRef}
        id={id}
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            onSubmit();
          } else if (e.key === "Escape") {
            e.preventDefault();
            if (value) onChange("");
            else e.currentTarget.blur();
          }
        }}
        placeholder="Search analyses"
        autoComplete="off"
        spellCheck={false}
        aria-keyshortcuts="/"
        className="peer h-10 w-full rounded-md border border-line bg-paper pr-9 pl-10 text-sm text-ink placeholder:text-muted focus:border-ink focus:outline-none [&::-webkit-search-cancel-button]:hidden"
      />
      {value ? (
        <button
          type="button"
          onClick={() => {
            onChange("");
            inputRef.current?.focus();
          }}
          aria-label="Clear search"
          className="absolute top-1/2 right-2 grid size-6 -translate-y-1/2 place-items-center rounded text-muted hover:bg-soft hover:text-ink"
        >
          <X className="size-3.5" aria-hidden />
        </button>
      ) : (
        <kbd
          aria-hidden
          className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 rounded border border-line px-1.5 font-sans text-[11px] leading-4 text-muted peer-focus:hidden"
        >
          /
        </kbd>
      )}
    </div>
  );
}

const typing = (target: EventTarget | null) =>
  target instanceof HTMLElement &&
  (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

export function Shell() {
  const [open, setOpen] = useState(false);
  const [rail, toggleRail] = useRail();
  const location = useLocation();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const desktopSearch = useRef<HTMLInputElement>(null);
  const mobileSearch = useRef<HTMLInputElement>(null);
  // Which search box to focus once it's on screen (after expanding the rail or opening the drawer).
  const [focusSearch, setFocusSearch] = useState<"desktop" | "mobile" | null>(null);
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

  const matches = searchRuns(runs, query);
  const searching = query.trim() !== "";
  const openFirstMatch = () => {
    if (matches[0]) navigate(`/runs/${matches[0].id}`);
  };

  const startSearch = useCallback(() => {
    if (window.matchMedia("(min-width: 64rem)").matches) {
      if (rail) toggleRail();
      setFocusSearch("desktop");
    } else {
      setOpen(true);
      setFocusSearch("mobile");
    }
  }, [rail, toggleRail]);

  useEffect(() => {
    if (!focusSearch) return;
    const input = (focusSearch === "desktop" ? desktopSearch : mobileSearch).current;
    if (input) {
      input.focus();
      input.select();
      setFocusSearch(null);
    }
  });

  // "/" jumps to the search box from anywhere except while typing.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "/" && !e.metaKey && !e.ctrlKey && !e.altKey && !typing(e.target)) {
        e.preventDefault();
        startSearch();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [startSearch]);

  const themeLabel = theme === "dark" ? "Light mode" : "Dark mode";
  const ThemeIcon = theme === "dark" ? Sun : Moon;
  const aiLabel = ready ? `${provider?.name ?? "AI"} ${modelLabel}` : "Connect an AI model";

  const nav = (mobile: boolean) => {
    const collapsed = !mobile && rail;
    return (
      <nav aria-label="Analyses" className="flex h-full flex-col gap-1 px-3 py-3">
        <div className="mb-2 flex h-10 items-center">
          {collapsed ? (
            // Rail: the logo sits in the icon column and turns into the expand button on hover or focus.
            <RailTip on label="Expand sidebar" detail={SHORTCUT}>
              <button
                onClick={toggleRail}
                aria-expanded={false}
                aria-controls="sidebar"
                aria-label="Expand sidebar"
                className={cx(slot, "group/logo h-10 rounded-md text-muted hover:bg-soft hover:text-ink")}
              >
                <Logo size={28} className="group-hover/logo:hidden group-focus-visible/logo:hidden" />
                <PanelLeftOpen className="hidden size-5 group-hover/logo:block group-focus-visible/logo:block" aria-hidden />
              </button>
            </RailTip>
          ) : (
            <>
              <NavLink to="/" className="flex h-10 min-w-0 flex-1 items-center">
                <span className={slot}>
                  <Logo size={28} />
                </span>
                <span className="truncate pl-1 text-lg font-semibold tracking-tight whitespace-nowrap">Review Insights</span>
              </NavLink>
              {mobile ? (
                <button onClick={() => setOpen(false)} aria-label="Close menu" className="grid size-8 shrink-0 place-items-center rounded-md text-muted hover:bg-soft hover:text-ink">
                  <X className="size-5" aria-hidden />
                </button>
              ) : (
                <button
                  onClick={toggleRail}
                  aria-expanded
                  aria-controls="sidebar"
                  aria-label="Collapse sidebar"
                  title={`Collapse sidebar (${SHORTCUT})`}
                  className="grid size-8 shrink-0 place-items-center rounded-md text-muted hover:bg-soft hover:text-ink"
                >
                  <PanelLeftClose className="size-5" aria-hidden />
                </button>
              )}
            </>
          )}
        </div>

        <RailTip on={collapsed} label="New analysis">
          <NavLink to="/new" className={cx(row, "h-10 bg-ink font-medium text-paper hover:opacity-90")}>
            <span className={slot}>
              <Plus className="size-5" aria-hidden />
            </span>
            <Label hidden={collapsed}>New analysis</Label>
          </NavLink>
        </RailTip>
        <RailTip on={collapsed} label="Benchmark against competitors">
          <NavLink to="/benchmark" className={({ isActive }) => navRow(isActive)}>
            <span className={cx(slot, "text-muted")}>
              <Columns3 className="size-5" aria-hidden />
            </span>
            <Label hidden={collapsed}>Benchmark against competitors</Label>
          </NavLink>
        </RailTip>

        {runs.length > 0 &&
          (collapsed ? (
            <div className="mt-2">
              <RailTip on label={searching ? `Search: ${query.trim()}` : "Search analyses"} detail="/">
              <button onClick={startSearch} aria-keyshortcuts="/" className={navRow(false)}>
                <span className={cx(slot, "text-muted")}>
                  <Search className="size-5" aria-hidden />
                  {searching && <span className="absolute -top-1 right-2 size-2 rounded-full bg-ink" aria-hidden />}
                </span>
                <Label hidden>Search analyses</Label>
              </button>
              </RailTip>
            </div>
          ) : (
            <div className="mt-2">
              <HistorySearch
                id={mobile ? "history-search-mobile" : "history-search"}
                value={query}
                onChange={setQuery}
                onSubmit={openFirstMatch}
                inputRef={mobile ? mobileSearch : desktopSearch}
              />
            </div>
          ))}

        {/* Same height in both states, so the history below doesn't move when collapsing. */}
        <div className="flex h-8 shrink-0 items-center">
          {collapsed ? (
            <>
              <span className="grid w-10 place-items-center" aria-hidden>
                <span className="h-px w-6 bg-line" />
              </span>
              <h2 className="sr-only">Past analyses</h2>
            </>
          ) : (
            <div className="flex w-full items-baseline justify-between gap-2 px-2">
              <h2 className="text-sm font-medium whitespace-nowrap text-muted">Past analyses</h2>
              {searching && (
                <span className="text-xs whitespace-nowrap tabular-nums text-muted" aria-live="polite">
                  {matches.length} of {runs.length}
                </span>
              )}
            </div>
          )}
        </div>

        <div className="-mx-1 min-h-0 flex-1 overflow-y-auto px-1">
          {isLoading ? (
            !collapsed && <p className="px-2 text-sm text-muted">Loading…</p>
          ) : runs.length === 0 ? (
            !collapsed && <p className="px-2 text-sm text-muted">Your analyses will appear here.</p>
          ) : matches.length === 0 ? (
            !collapsed && (
              <div className="flex flex-col items-start gap-1 px-2 py-2 text-sm">
                <p>No analyses match “{query.trim()}”.</p>
                <p className="text-muted">Try an app name, developer, country or AI model.</p>
                <button onClick={() => setQuery("")} className="mt-1 font-medium underline underline-offset-2 hover:text-muted">
                  Clear search
                </button>
              </div>
            )
          ) : (
            <div className="flex flex-col gap-0.5">
              {matches.map((run) => (
                <HistoryItem key={run.id} run={run} query={query} rail={collapsed} />
              ))}
            </div>
          )}
        </div>

        <div className="mt-1 flex flex-col gap-1 border-t border-line pt-2">
          <RailTip on={collapsed} label={aiLabel} detail="AI settings">
            <NavLink to="/settings" className={({ isActive }) => navRow(isActive)}>
              <span className={cx(slot, "text-muted")}>
                <Settings2 className="size-5" aria-hidden />
                {!ready && <span className="absolute -top-1 right-2 size-2 rounded-full bg-warn" aria-hidden />}
              </span>
              <Label hidden={collapsed}>
                {ready ? (
                  <>
                    {provider?.name} <span className="text-muted">{modelLabel}</span>
                  </>
                ) : (
                  <span className="text-warn">Connect an AI model</span>
                )}
              </Label>
            </NavLink>
          </RailTip>
          <RailTip on={collapsed} label="Use in Claude, ChatGPT…">
            <NavLink to="/connect" className={({ isActive }) => navRow(isActive)}>
              <span className={cx(slot, "text-muted")}>
                <Plug className="size-5" aria-hidden />
              </span>
              <Label hidden={collapsed}>Use in Claude, ChatGPT…</Label>
            </NavLink>
          </RailTip>
          <RailTip on={collapsed} label={themeLabel}>
            <button onClick={toggle} className={navRow(false)}>
              <span className={cx(slot, "text-muted")}>
                <ThemeIcon className="size-5" aria-hidden />
              </span>
              <Label hidden={collapsed}>{themeLabel}</Label>
            </button>
          </RailTip>
          <RailTip on={collapsed} label="About">
            <NavLink to="/about" className={({ isActive }) => navRow(isActive)}>
              <span className={slot}>
                <AuthorAvatar size={22} />
              </span>
              <Label hidden={collapsed}>About</Label>
            </NavLink>
          </RailTip>
        </div>
      </nav>
    );
  };

  return (
    <div className="flex h-full">
      <aside
        id="sidebar"
        className={cx(
          "hidden shrink-0 overflow-hidden border-r border-line bg-panel transition-[width] duration-200 ease-out motion-reduce:transition-none lg:block print:hidden",
          rail ? "w-16" : "w-72",
        )}
      >
        {nav(false)}
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-ink/30" onClick={() => setOpen(false)} aria-hidden />
          <aside className="absolute inset-y-0 left-0 w-72 bg-panel shadow-xl">{nav(true)}</aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b border-line bg-panel px-4 py-3 lg:hidden print:hidden">
          <button onClick={() => setOpen(true)} aria-label="Open menu" className="rounded p-1 text-muted hover:text-ink">
            <Menu className="size-5" />
          </button>
          <Logo size={24} />
          <span className="font-semibold">Review Insights</span>
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
