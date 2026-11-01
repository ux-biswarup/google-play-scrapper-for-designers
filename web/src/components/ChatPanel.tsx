import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowUp,
  Check,
  Copy,
  History,
  Loader2,
  Pencil,
  RotateCcw,
  Search,
  ScanSearch,
  Square,
  SquarePen,
  Trash2,
  X,
} from "lucide-react";
import { chatApi, type ChatEvent, type ChatSession, type ChatTurn, type CitedReview, type Run } from "../lib/api";
import { relativeTime, shortDate } from "../lib/format";
import { highlightParts } from "../lib/runSearch";
import { toLLMConfig, useConnection } from "../lib/settings";
import { AppIcon } from "./Shell";
import { Notice, Stars, cx } from "./ui";

const CITATION = /\[\[r:([^\]\s]+)\]\]/g;
const MAX_CHARS = 4000;

type AssistantTurn = Extract<ChatTurn, { role: "assistant" }>;

/** Number citations in order of first appearance and turn them into in-page links. */
function withCitations(text: string): { markdown: string; order: string[] } {
  const order: string[] = [];
  const markdown = text.replace(CITATION, (_match, id: string) => {
    let n = order.indexOf(id) + 1;
    if (n === 0) n = order.push(id);
    return `[${n}](#cite-${id})`;
  });
  return { markdown, order };
}

/** Answer text without citation markers, for copying into docs and tickets. */
const plainAnswer = (text: string) => text.replace(CITATION, "").replace(/[ \t]+\n/g, "\n").trim();

function Evidence({ review, n, anchor }: { review: CitedReview | undefined; n: number; anchor: string }) {
  return (
    <li id={anchor} className="flex scroll-mt-4 gap-3 rounded-md border border-line p-3 target:border-ink target:bg-soft">
      <span className="text-xs font-semibold tabular-nums text-muted">{n}</span>
      {review ? (
        <figure className="min-w-0 flex-1">
          <blockquote className="font-quote leading-relaxed">{review.text}</blockquote>
          <figcaption className="mt-1 flex flex-wrap items-center gap-x-3 text-xs text-muted">
            <Stars value={review.rating} />
            <span>{shortDate(review.date)}</span>
            {review.app_version && review.app_version !== "unknown" && <span>Version {review.app_version}</span>}
          </figcaption>
        </figure>
      ) : (
        <span className="text-sm text-muted">This review isn't in the assistant's lookups.</span>
      )}
    </li>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        await navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-muted hover:bg-soft hover:text-ink"
    >
      {copied ? <Check className="size-3" aria-hidden /> : <Copy className="size-3" aria-hidden />}
      {copied ? "Copied" : "Copy answer"}
    </button>
  );
}

function AssistantMessage({
  turn,
  index,
  streaming,
  onRetry,
}: {
  turn: AssistantTurn;
  index: number;
  streaming: boolean;
  onRetry?: () => void;
}) {
  const { markdown, order } = useMemo(() => withCitations(turn.text), [turn.text]);
  const anchor = (id: string) => `cite-${index}-${id}`;
  const components: Components = {
    a: ({ href, children }) => {
      if (href?.startsWith("#cite-")) {
        const id = href.slice(6);
        return (
          <a
            href={`#${anchor(id)}`}
            className="mx-0.5 inline-grid min-w-[1.15rem] place-items-center rounded bg-soft px-1 align-text-top text-[0.7rem] font-semibold text-ink no-underline hover:bg-hl"
            aria-label={`Source ${String(children)}`}
          >
            {children}
          </a>
        );
      }
      return (
        <a href={href} target="_blank" rel="noreferrer" className="underline underline-offset-2">
          {children}
        </a>
      );
    },
  };

  return (
    <div className="flex flex-col gap-3">
      {turn.steps.length > 0 && (
        <ul className="flex flex-col gap-1 text-xs text-muted" aria-label="Steps taken">
          {turn.steps.map((step) => (
            <li key={step.id} className="flex items-center gap-1.5">
              {step.running ? (
                <Loader2 className="size-3 animate-spin" aria-hidden />
              ) : step.ok ? (
                <Check className="size-3" aria-hidden />
              ) : (
                <X className="size-3 text-neg" aria-hidden />
              )}
              {step.label}
            </li>
          ))}
        </ul>
      )}
      {turn.text ? (
        <div className="chat-prose">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
            {markdown}
          </ReactMarkdown>
        </div>
      ) : (
        streaming && <Loader2 className="size-4 animate-spin text-muted" aria-label="Thinking" />
      )}
      {turn.error && (
        <div className="flex flex-col items-start gap-2">
          <Notice tone="error" title="The assistant stopped">{turn.error}</Notice>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1 text-sm hover:bg-soft"
            >
              <RotateCcw className="size-3.5" aria-hidden /> Try again
            </button>
          )}
        </div>
      )}
      {!streaming && order.length > 0 && (
        <section aria-label="Evidence">
          <h4 className="mb-2 text-xs font-medium text-muted">Evidence</h4>
          <ol className="flex flex-col gap-2">
            {order.map((id, i) => (
              <Evidence key={id} review={turn.reviews[id]} n={i + 1} anchor={anchor(id)} />
            ))}
          </ol>
        </section>
      )}
      {!streaming && turn.text && (
        <div className="-mt-1">
          <CopyButton text={plainAnswer(turn.text)} />
        </div>
      )}
    </div>
  );
}

function applyEvent(turn: AssistantTurn, event: ChatEvent): AssistantTurn {
  switch (event.type) {
    case "text":
      return { ...turn, text: turn.text + event.delta };
    case "tool":
      return { ...turn, steps: [...turn.steps, { id: event.id, label: event.label, ok: true, running: true }] };
    case "tool_result":
      return {
        ...turn,
        steps: turn.steps.map((s) => (s.id === event.id ? { ...s, ok: event.ok, running: false } : s)),
        reviews: { ...turn.reviews, ...event.reviews },
      };
    case "error":
      return { ...turn, error: event.message };
    default:
      return turn;
  }
}

/** Suggestion tags about risks read warm, strengths read positive; the rest stay neutral. */
const TAG_TONE: Record<string, string> = {
  "Top problem": "bg-neg/10 text-neg",
  Rising: "bg-neg/10 text-neg",
  "Churn risk": "bg-neg/10 text-neg",
  Money: "bg-warn/10 text-warn",
  Strength: "bg-pos/10 text-pos",
};

// ---- tabs ----------------------------------------------------------------------------------------

/** A tab shows a saved chat (its id) or a new, not-yet-saved chat ("new-…"). */
type TabId = string;
const isNew = (id: TabId) => id.startsWith("new-");
const newTabId = () => `new-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
type Tabs = { open: TabId[]; active: TabId };

/** Open tabs per analysis, remembered across visits. New, empty chats aren't worth remembering. */
function useTabs(runId: string, sessions: ChatSession[] | undefined) {
  const key = `ri.chat-tabs.${runId}`;
  const restored = useRef(false);
  const [tabs, setTabs] = useState<Tabs>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(key) ?? "null") as Tabs | null;
      if (saved?.open?.length) {
        restored.current = true;
        return saved;
      }
    } catch {
      // ignore unreadable state
    }
    const first = newTabId();
    return { open: [first], active: first };
  });

  useEffect(() => {
    if (!sessions) return;
    // First visit with earlier chats: continue the most recent one instead of starting blank.
    if (!restored.current && sessions.length > 0) {
      restored.current = true;
      setTabs((t) => (t.open.length === 1 && isNew(t.open[0]) ? { open: [sessions[0].id], active: sessions[0].id } : t));
      return;
    }
    restored.current = true;
    // Drop tabs whose chat was deleted (elsewhere or in an older session of the app).
    const known = new Set(sessions.map((s) => s.id));
    setTabs((t) => {
      const open = t.open.filter((id) => isNew(id) || known.has(id));
      if (open.length === t.open.length) return t;
      const next = open.length ? open : [newTabId()];
      return { open: next, active: next.includes(t.active) ? t.active : next[next.length - 1] };
    });
  }, [sessions]);

  useEffect(() => {
    const saved = tabs.open.filter((id) => !isNew(id));
    localStorage.setItem(key, JSON.stringify({ open: saved, active: isNew(tabs.active) ? saved[0] : tabs.active }));
  }, [key, tabs]);

  const activate = useCallback((id: TabId) => setTabs((t) => ({ open: t.open.includes(id) ? t.open : [...t.open, id], active: id })), []);
  const close = useCallback((id: TabId) => {
    setTabs((t) => {
      const i = t.open.indexOf(id);
      const open = t.open.filter((x) => x !== id);
      if (open.length === 0) {
        const fresh = newTabId();
        return { open: [fresh], active: fresh };
      }
      return { open, active: t.active === id ? open[Math.max(0, i - 1)] : t.active };
    });
  }, []);
  const replace = useCallback(
    (from: TabId, to: TabId) =>
      setTabs((t) => ({ open: t.open.map((x) => (x === from ? to : x)), active: t.active === from ? to : t.active })),
    [],
  );
  return { tabs, activate, close, replace };
}

// ---- history dropdown ----------------------------------------------------------------------------

type Listed = ChatSession & { snippet?: string | null };

const DAY = 86_400_000;
function dateGroup(iso: string, now = new Date()): string {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const t = new Date(iso).getTime();
  if (t >= today) return "Today";
  if (t >= today - DAY) return "Yesterday";
  if (t >= today - 7 * DAY) return "Previous 7 days";
  if (t >= today - 30 * DAY) return "Previous 30 days";
  return "Older";
}

function Mark({ text, query }: { text: string; query: string }) {
  return (
    <>
      {highlightParts(text, query).map((p, i) =>
        p.match ? (
          <mark key={i} className="rounded-sm bg-hl/40 text-ink">
            {p.text}
          </mark>
        ) : (
          p.text
        ),
      )}
    </>
  );
}

/** Drops down from the History button: search across titles, questions and answers, grouped by date. */
function HistoryMenu({
  runId,
  sessions,
  openIds,
  onOpen,
  onDeleted,
  onClose,
  anchor,
}: {
  runId: string;
  sessions: ChatSession[];
  openIds: TabId[];
  onOpen: (id: string) => void;
  onDeleted: (id: string) => void;
  onClose: (returnFocus: boolean) => void;
  anchor: React.RefObject<HTMLButtonElement | null>;
}) {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const deferred = useDeferredValue(query.trim());
  const search = useQuery({
    queryKey: ["chat-sessions", runId, "search", deferred],
    queryFn: () => chatApi.sessions(runId, deferred),
    enabled: deferred.length > 0,
    placeholderData: keepPreviousData,
  });
  const [editing, setEditing] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const panel = useRef<HTMLDivElement>(null);
  const searchBox = useRef<HTMLInputElement>(null);
  useEffect(() => searchBox.current?.focus(), []);
  // Close when clicking anywhere outside the dropdown (the History button toggles it itself).
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (!panel.current?.contains(target) && !anchor.current?.contains(target)) onClose(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [anchor, onClose]);

  const shown: Listed[] = deferred ? (search.data?.sessions ?? []) : sessions;
  const groups: [string, Listed[]][] = [];
  for (const s of shown) {
    const g = dateGroup(s.updated_at);
    const last = groups[groups.length - 1];
    if (last && last[0] === g) last[1].push(s);
    else groups.push([g, [s]]);
  }
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["chat-sessions", runId] });

  async function rename(id: string) {
    const next = title.trim();
    setEditing(null);
    if (!next) return;
    await chatApi.rename(runId, id, next);
    refresh();
  }

  async function remove(s: ChatSession) {
    if (!window.confirm(`Delete “${s.title}”? This can't be undone.`)) return;
    await chatApi.remove(runId, s.id);
    onDeleted(s.id);
    queryClient.removeQueries({ queryKey: ["chat-session", runId, s.id] });
    refresh();
  }

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape" && !editing) {
      e.preventDefault();
      onClose(true);
    }
  };

  return (
      <div
        ref={panel}
        id="chat-history"
        role="dialog"
        aria-labelledby="chat-history-title"
        onKeyDown={onKeyDown}
        className="absolute top-[calc(100%+4px)] right-2 z-30 flex max-h-[min(30rem,70vh)] w-[22rem] max-w-[calc(100%-1rem)] origin-top-right animate-[pop-in_140ms_ease-out] flex-col overflow-hidden rounded-xl border border-line bg-panel shadow-xl"
      >
        <h3 id="chat-history-title" className="sr-only">
          Chat history
        </h3>

        <div className="shrink-0 border-b border-line px-3 pt-3 pb-2">
          <div role="search" className="relative">
            <label htmlFor="chat-history-search" className="sr-only">
              Search chats
            </label>
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" aria-hidden />
            <input
              ref={searchBox}
              id="chat-history-search"
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape" && query) {
                  e.preventDefault();
                  e.stopPropagation();
                  setQuery("");
                } else if (e.key === "Enter" && shown[0]) {
                  e.preventDefault();
                  onOpen(shown[0].id);
                }
              }}
              placeholder="Search chats and answers"
              autoComplete="off"
              spellCheck={false}
              className="h-9 w-full rounded-lg border border-line bg-paper pr-8 pl-9 text-sm placeholder:text-muted focus:border-ink focus:bg-panel focus:outline-none [&::-webkit-search-cancel-button]:hidden"
            />
            {query && (
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  searchBox.current?.focus();
                }}
                aria-label="Clear search"
                className="absolute top-1/2 right-1.5 grid size-6 -translate-y-1/2 place-items-center rounded text-muted hover:bg-soft hover:text-ink"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            )}
          </div>
          <p className="mt-2 px-1 text-xs text-muted" aria-live="polite">
            {!deferred
              ? "Chats about this analysis only. Other analyses have their own."
              : search.isFetching && !search.data
                ? "Searching…"
                : shown.length > 0
                  ? `${shown.length} ${shown.length === 1 ? "chat" : "chats"} match`
                  : "No matches"}
          </p>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-2 pt-1 pb-2">
          {sessions.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-muted">No chats yet. Your conversations about this analysis appear here.</p>
          ) : deferred && search.data && shown.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm">
              <p>No chats mention “{deferred}”.</p>
              <button onClick={() => setQuery("")} className="mt-2 font-medium underline underline-offset-2 hover:text-muted">
                Clear search
              </button>
            </div>
          ) : (
            groups.map(([group, items]) => (
              <section key={group} aria-label={group} className="mt-2 first:mt-0">
                <h4 className="px-3 pt-2 pb-1 text-xs font-medium text-muted">{group}</h4>
                <ul className="flex flex-col">
                  {items.map((s) => (
                    <li key={s.id} className="group flex items-center gap-1 rounded-md hover:bg-soft">
                      {editing === s.id ? (
                        <form
                          className="flex-1 p-1.5"
                          onSubmit={(e) => {
                            e.preventDefault();
                            rename(s.id);
                          }}
                        >
                          <label htmlFor={`rename-${s.id}`} className="sr-only">
                            Chat name
                          </label>
                          <input
                            id={`rename-${s.id}`}
                            autoFocus
                            value={title}
                            maxLength={120}
                            onChange={(e) => setTitle(e.target.value)}
                            onBlur={() => rename(s.id)}
                            onKeyDown={(e) => {
                              if (e.key === "Escape") {
                                e.stopPropagation();
                                setEditing(null);
                              }
                            }}
                            className="h-8 w-full rounded border border-ink bg-paper px-2 text-sm focus:outline-none"
                          />
                        </form>
                      ) : (
                        <button onClick={() => onOpen(s.id)} className="flex min-w-0 flex-1 flex-col px-3 py-2 text-left">
                          <span className="flex items-center gap-1.5">
                            <span className="truncate text-sm font-medium">
                              <Mark text={s.title} query={deferred} />
                            </span>
                            {openIds.includes(s.id) && (
                              <span className="shrink-0 rounded-full bg-soft px-1.5 text-[10px] font-medium text-muted group-hover:bg-panel">Open</span>
                            )}
                          </span>
                          {s.snippet && (
                            <span className="mt-0.5 line-clamp-2 text-xs text-muted">
                              <Mark text={s.snippet} query={deferred} />
                            </span>
                          )}
                          <span className="mt-0.5 text-xs text-muted">
                            {relativeTime(s.updated_at)}, {s.questions} {s.questions === 1 ? "question" : "questions"}
                          </span>
                        </button>
                      )}
                      {editing !== s.id && (
                        <div className="flex shrink-0 pr-1 opacity-0 group-focus-within:opacity-100 group-hover:opacity-100">
                          <button
                            onClick={() => {
                              setTitle(s.title);
                              setEditing(s.id);
                            }}
                            aria-label={`Rename “${s.title}”`}
                            className="grid size-7 place-items-center rounded text-muted hover:bg-panel hover:text-ink"
                          >
                            <Pencil className="size-3.5" aria-hidden />
                          </button>
                          <button
                            onClick={() => remove(s)}
                            aria-label={`Delete “${s.title}”`}
                            className="grid size-7 place-items-center rounded text-muted hover:bg-panel hover:text-neg"
                          >
                            <Trash2 className="size-3.5" aria-hidden />
                          </button>
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </section>
            ))
          )}
        </div>
      </div>
  );
}

// ---- panel ------------------------------------------------------------------------------------

export function ChatPanel({ run, onClose }: { run: Run; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { connection, ready, provider, modelLabel } = useConnection();
  const appName = run.app.title ?? run.app.store_id;
  const list = useQuery({ queryKey: ["chat-sessions", run.id], queryFn: () => chatApi.sessions(run.id) });
  const sessions = list.data?.sessions;
  const { tabs, activate, close, replace } = useTabs(run.id, sessions);
  const active = tabs.active;
  const [historyOpen, setHistoryOpen] = useState(false);
  const historyButton = useRef<HTMLButtonElement>(null);
  const closeHistory = useCallback((returnFocus = true) => {
    setHistoryOpen(false);
    if (returnFocus) historyButton.current?.focus();
  }, []);

  // Per-tab state, so replies keep streaming and drafts survive while you look at another tab.
  const [drafts, setDrafts] = useState<Record<TabId, string>>({});
  const [pending, setPending] = useState<Record<TabId, ChatTurn[]>>({});
  const [busy, setBusy] = useState<Record<TabId, boolean>>({});
  const aborts = useRef(new Map<TabId, AbortController>());
  const bottom = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const tabRefs = useRef(new Map<TabId, HTMLButtonElement>());
  const tabStrip = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const tab = tabRefs.current.get(active)?.parentElement;
    const strip = tabStrip.current;
    if (!tab || !strip) return;
    // Scroll only the tab row (not the page), just enough to show the whole tab.
    const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const left = tab.offsetLeft - strip.offsetLeft;
    if (left < strip.scrollLeft) strip.scrollTo({ left: left - 8, behavior: smooth ? "smooth" : "auto" });
    else if (left + tab.offsetWidth > strip.scrollLeft + strip.clientWidth)
      strip.scrollTo({ left: left + tab.offsetWidth - strip.clientWidth + 12, behavior: smooth ? "smooth" : "auto" });
  }, [active, tabs.open.length]);

  const chat = useQuery({
    queryKey: ["chat-session", run.id, active],
    queryFn: () => chatApi.get(run.id, active),
    enabled: !isNew(active),
  });
  const turns = [...(isNew(active) ? [] : (chat.data?.turns ?? [])), ...(pending[active] ?? [])];
  const isBusy = !!busy[active];
  const draft = drafts[active] ?? "";
  const titleOf = (id: TabId) => (isNew(id) ? "New chat" : (sessions?.find((s) => s.id === id)?.title ?? "Chat"));

  useEffect(() => {
    // Follow the conversation; an empty chat stays at the top so its intro and suggestions are visible.
    // Block body on purpose: scrollIntoView returns a Promise in newer browsers, and an effect must not return one.
    if (turns.length > 0) {
      bottom.current?.scrollIntoView({ block: "end" });
    }
  }, [turns.length, pending, active]);
  useEffect(() => {
    const controllers = aborts.current;
    return () => controllers.forEach((c) => c.abort());
  }, []);
  useEffect(() => {
    input.current?.focus();
  }, [active]);

  const setDraft = (id: TabId, text: string) => setDrafts((d) => ({ ...d, [id]: text }));

  function newChat() {
    setHistoryOpen(false);
    // Reuse an empty new chat instead of piling up blank tabs.
    const blank = tabs.open.find((id) => isNew(id) && !pending[id]?.length);
    activate(blank ?? newTabId());
  }

  async function send(text: string) {
    const message = text.trim();
    const tab = active;
    if (!message || busy[tab] || !connection || message.length > MAX_CHARS) return;
    setDraft(tab, "");
    let id = tab;
    let reply: AssistantTurn = { role: "assistant", text: "", steps: [], reviews: {} };
    const show = (turn: AssistantTurn) => setPending((p) => ({ ...p, [id]: [{ role: "user", text: message }, turn] }));
    show(reply);
    setBusy((b) => ({ ...b, [id]: true }));
    const controller = new AbortController();
    let savedError = false; // errors reported in the stream are saved with the chat; network errors aren't
    try {
      if (isNew(tab)) {
        // Save the chat on its first question, then move this tab's state to the saved id.
        id = (await chatApi.create(run.id)).id;
        setPending((p) => ({ ...p, [id]: p[tab] ?? [], [tab]: [] }));
        setBusy((b) => ({ ...b, [id]: true, [tab]: false }));
        replace(tab, id);
      }
      aborts.current.set(id, controller);
      for await (const event of chatApi.send(run.id, id, message, toLLMConfig(connection), controller.signal)) {
        if (event.type === "error") savedError = true;
        reply = applyEvent(reply, event);
        show(reply);
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        reply = { ...reply, error: error instanceof Error ? error.message : String(error) };
        show(reply);
      }
    } finally {
      aborts.current.delete(id);
      setBusy((b) => ({ ...b, [id]: false }));
      if (!isNew(id)) {
        await queryClient.invalidateQueries({ queryKey: ["chat-session", run.id, id] });
        queryClient.invalidateQueries({ queryKey: ["chat-sessions", run.id] });
      }
      // Show the saved transcript; keep a failed reply on screen only when the server couldn't save it.
      setPending((p) => ({ ...p, [id]: reply.error && !savedError ? (p[id] ?? []) : [] }));
    }
  }

  const lastQuestion = [...turns].reverse().find((t) => t.role === "user")?.text;
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(draft);
    } else if (e.key === "Escape" && isBusy) {
      e.preventDefault();
      aborts.current.get(active)?.abort();
    } else if (e.key === "ArrowUp" && !draft && lastQuestion) {
      e.preventDefault();
      setDraft(active, lastQuestion);
    }
  };

  const onTabKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const i = tabs.open.indexOf(active);
    const next = tabs.open[(i + (e.key === "ArrowRight" ? 1 : -1) + tabs.open.length) % tabs.open.length];
    activate(next);
    tabRefs.current.get(next)?.focus();
  };

  const over = draft.length > MAX_CHARS;

  return (
    <aside aria-label={`Assistant for ${appName}`} className="relative flex h-full flex-col bg-panel">
      {/* One row on a tinted ribbon: open chats as compact tags (the active one is white like the chat below),
          then New chat, History and Close. */}
      <header className="relative flex h-11 shrink-0 items-center gap-1 border-b border-line bg-soft pl-1.5">
        <div
          ref={tabStrip}
          role="tablist"
          aria-label="Open chats"
          onKeyDown={onTabKey}
          className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto px-1 [mask-image:linear-gradient(to_right,transparent,black_6px,black_calc(100%-10px),transparent)]"
        >
          {tabs.open.map((id) => {
            const selected = id === active;
            return (
              <div
                key={id}
                className={cx(
                  "group flex h-7 max-w-[10rem] shrink-0 items-center rounded-md text-[13px] transition-colors",
                  selected
                    ? "bg-panel text-ink shadow-sm ring-1 ring-line"
                    : "text-muted hover:bg-panel/60 hover:text-ink",
                )}
              >
                <button
                  ref={(el) => {
                    if (el) tabRefs.current.set(id, el);
                    else tabRefs.current.delete(id);
                  }}
                  role="tab"
                  aria-selected={selected}
                  tabIndex={id === active ? 0 : -1}
                  onClick={() => activate(id)}
                  title={titleOf(id)}
                  className="flex h-full min-w-0 items-center gap-1.5 rounded-md pr-0.5 pl-2.5 focus-visible:outline-offset-0"
                >
                  {busy[id] && <Loader2 className="size-3 shrink-0 animate-spin" aria-label="Answering" />}
                  <span className={cx("truncate", selected && "font-medium")}>{titleOf(id)}</span>
                </button>
                <button
                  onClick={() => close(id)}
                  aria-label={`Close tab “${titleOf(id)}”`}
                  title="Close tab (the chat stays in history)"
                  className={cx(
                    "mr-1 grid size-4 shrink-0 place-items-center rounded-sm text-muted hover:bg-soft hover:text-ink",
                    !selected && "opacity-0 group-hover:opacity-100 focus:opacity-100",
                  )}
                >
                  <X className="size-3" aria-hidden />
                </button>
              </div>
            );
          })}
        </div>
        <div className="flex shrink-0 items-center gap-0.5 pr-1.5">
          <button onClick={newChat} title="New chat" className="grid size-7 place-items-center rounded-md text-muted hover:bg-panel hover:text-ink">
            <SquarePen className="size-4" aria-hidden />
            <span className="sr-only">New chat</span>
          </button>
          <button
            ref={historyButton}
            onClick={() => (historyOpen ? closeHistory() : setHistoryOpen(true))}
            aria-haspopup="dialog"
            aria-controls={historyOpen ? "chat-history" : undefined}
            aria-expanded={historyOpen}
            title="Chat history"
            className={cx(
              "grid size-7 place-items-center rounded-md text-muted hover:bg-panel hover:text-ink",
              historyOpen && "bg-panel text-ink shadow-sm ring-1 ring-line",
            )}
          >
            <History className="size-4" aria-hidden />
            <span className="sr-only">Chat history</span>
          </button>
          <button onClick={onClose} title="Close assistant" className="grid size-7 place-items-center rounded-md text-muted hover:bg-panel hover:text-ink">
            <X className="size-4" aria-hidden />
            <span className="sr-only">Close assistant</span>
          </button>
        </div>
        {historyOpen && (
          <HistoryMenu
            runId={run.id}
            sessions={sessions ?? []}
            openIds={tabs.open}
            onOpen={(id) => {
              activate(id);
              setHistoryOpen(false);
            }}
            onDeleted={close}
            onClose={closeHistory}
            anchor={historyButton}
          />
        )}
      </header>


      <>
          <div role="tabpanel" aria-label={titleOf(active)} className="min-h-0 flex-1 overflow-y-auto px-4 py-4" aria-live="polite">
            {!isNew(active) && chat.isLoading ? (
              <Loader2 className="size-4 animate-spin text-muted" aria-label="Loading" />
            ) : turns.length === 0 ? (
              // Empty chat: sits at the bottom, right above the composer, where the eye already is.
              <div className="flex min-h-full flex-col justify-end gap-5">
                <div className="flex items-center gap-3">
                  <AppIcon src={run.app.icon_url} title={appName} size={40} />
                  <div className="min-w-0">
                    <h3 className="truncate text-base font-semibold tracking-tight">Ask about {appName}</h3>
                    <p className="text-sm text-muted">Answers use its {run.review_count} reviews and quote them.</p>
                  </div>
                </div>
                {(list.data?.suggestions.length ?? 0) > 0 && (
                  <div>
                    <h4 className="mb-1.5 px-1 text-xs font-medium text-muted">Try asking</h4>
                    <ul className="flex flex-col gap-1">
                      {list.data!.suggestions.map((s) => (
                        <li key={s.text}>
                          <button
                            onClick={() => send(s.text)}
                            disabled={!ready || isBusy}
                            className="group flex w-full items-start gap-2 rounded-lg border border-line bg-panel px-3 py-2 text-left text-sm transition-colors hover:border-muted/60 hover:bg-soft disabled:opacity-50"
                          >
                            <span className="min-w-0 flex-1">
                              {s.text}
                              <span
                                className={cx(
                                  "ml-1.5 inline-block rounded-full px-1.5 align-[1px] text-[10px] font-medium whitespace-nowrap",
                                  TAG_TONE[s.tag] ?? "bg-soft text-muted group-hover:bg-panel",
                                )}
                              >
                                {s.tag}
                              </span>
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col gap-6">
                {turns.map((turn, i) =>
                  turn.role === "user" ? (
                    <p key={i} className="ml-8 self-end rounded-2xl rounded-br-md bg-soft px-3.5 py-2 text-sm whitespace-pre-wrap">
                      {turn.text}
                    </p>
                  ) : (
                    <AssistantMessage
                      key={i}
                      turn={turn}
                      index={i}
                      streaming={isBusy && i === turns.length - 1}
                      onRetry={
                        turn.error && i === turns.length - 1 && !isBusy && ready && turns[i - 1]?.role === "user"
                          ? () => send(turns[i - 1].text)
                          : undefined
                      }
                    />
                  ),
                )}
              </div>
            )}
            <div ref={bottom} />
          </div>

          <form
            className="p-3"
            onSubmit={(e) => {
              e.preventDefault();
              send(draft);
            }}
          >
            {!ready ? (
              <div className="rounded-xl border border-dashed border-line px-4 py-3 text-sm text-muted">
                <Link to="/settings" className="font-medium text-ink underline underline-offset-2">
                  Connect an AI model
                </Link>{" "}
                to ask questions about {appName}.
              </div>
            ) : (
              <div className="rounded-2xl border border-muted/35 bg-panel shadow-[0_1px_2px_rgb(0_0_0/0.04),0_6px_16px_-6px_rgb(0_0_0/0.08)] transition-[border-color,box-shadow] hover:border-muted/60 focus-within:border-ink focus-within:ring-4 focus-within:ring-ink/5">
                {/* The whole composer shows focus (border and ring), so the text box itself needs no outline. */}
                <label htmlFor="chat-input" className="sr-only">
                  Ask about {appName}
                </label>
                <textarea
                  id="chat-input"
                  ref={input}
                  rows={1}
                  value={draft}
                  onChange={(e) => setDraft(active, e.target.value)}
                  onKeyDown={onKeyDown}
                  placeholder={`Ask about ${appName}'s reviews`}
                  aria-describedby="chat-input-hint"
                  className="block max-h-48 min-h-12 w-full resize-none bg-transparent px-4 pt-3 pb-1 text-[0.95rem] leading-relaxed text-ink outline-none [field-sizing:content] placeholder:text-muted/90 focus-visible:outline-none"
                />
                <div className="flex items-center gap-1.5 px-2 pb-2">
                  <span
                    title={`Answers use only the ${run.review_count} reviews in this analysis of ${appName}`}
                    className="inline-flex min-w-0 items-center gap-1 rounded-full border border-line px-2 py-0.5 text-xs text-muted"
                  >
                    <ScanSearch className="size-3.5 shrink-0" aria-hidden />
                    <span className="truncate">This analysis only</span>
                  </span>
                  <Link
                    to="/settings"
                    title="Change AI model"
                    className="inline-flex min-w-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs text-muted hover:bg-soft hover:text-ink"
                  >
                    <span className="truncate">{provider?.id === "chatgpt" ? "ChatGPT plan" : modelLabel}</span>
                  </Link>
                  <span className="flex-1" />
                  {draft.length > MAX_CHARS - 500 && (
                    <span className={cx("text-xs tabular-nums", over ? "text-neg" : "text-muted")}>
                      {draft.length}/{MAX_CHARS}
                    </span>
                  )}
                  {isBusy ? (
                    <button
                      type="button"
                      onClick={() => aborts.current.get(active)?.abort()}
                      title="Stop answering (Esc)"
                      className="grid size-8 place-items-center rounded-full bg-ink text-paper hover:opacity-90"
                    >
                      <Square className="size-3 fill-current" aria-hidden />
                      <span className="sr-only">Stop answering</span>
                    </button>
                  ) : (
                    <button
                      type="submit"
                      disabled={!draft.trim() || over}
                      title="Send (Enter)"
                      className="grid size-8 place-items-center rounded-full bg-ink text-paper transition-colors hover:opacity-90 disabled:bg-soft disabled:text-muted disabled:hover:opacity-100"
                    >
                      <ArrowUp className="size-4" aria-hidden />
                      <span className="sr-only">Send</span>
                    </button>
                  )}
                </div>
              </div>
            )}
            {ready && (
              <p id="chat-input-hint" className="mt-1.5 px-1 text-[11px] text-muted">
                Enter to send, Shift+Enter for a new line, ↑ for your last question.
              </p>
            )}
          </form>
      </>
    </aside>
  );
}
