import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowUp,
  Check,
  Copy,
  History,
  Loader2,
  MessageSquare,
  Pencil,
  Plus,
  ScanSearch,
  Sparkles,
  Square,
  SquarePen,
  Trash2,
  X,
} from "lucide-react";
import { chatApi, type ChatEvent, type ChatSession, type ChatTurn, type CitedReview, type Run } from "../lib/api";
import { relativeTime, shortDate } from "../lib/format";
import { toLLMConfig, useConnection } from "../lib/settings";
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

function AssistantMessage({ turn, index, streaming }: { turn: AssistantTurn; index: number; streaming: boolean }) {
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
      {turn.error && <Notice tone="error" title="The assistant stopped">{turn.error}</Notice>}
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

// ---- history -----------------------------------------------------------------------------------

function HistoryView({
  runId,
  sessions,
  openIds,
  onOpen,
  onDeleted,
}: {
  runId: string;
  sessions: ChatSession[];
  openIds: TabId[];
  onOpen: (id: string) => void;
  onDeleted: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const shown = sessions.filter((s) => s.title.toLowerCase().includes(filter.trim().toLowerCase()));
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

  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
      {sessions.length > 6 && (
        <div className="mb-3 px-1">
          <label htmlFor="chat-history-filter" className="sr-only">
            Filter chats
          </label>
          <input
            id="chat-history-filter"
            type="search"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter chats"
            className="h-9 w-full rounded-md border border-line bg-paper px-3 text-sm placeholder:text-muted focus:border-ink focus:outline-none"
          />
        </div>
      )}
      {sessions.length === 0 ? (
        <p className="px-1 py-6 text-center text-sm text-muted">No chats yet. Your conversations about this analysis appear here.</p>
      ) : shown.length === 0 ? (
        <p className="px-1 py-6 text-center text-sm text-muted">No chats match “{filter.trim()}”.</p>
      ) : (
        <ul className="flex flex-col gap-0.5">
          {shown.map((s) => (
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
                    onKeyDown={(e) => e.key === "Escape" && setEditing(null)}
                    className="h-8 w-full rounded border border-ink bg-paper px-2 text-sm focus:outline-none"
                  />
                </form>
              ) : (
                <button onClick={() => onOpen(s.id)} className="flex min-w-0 flex-1 items-start gap-2.5 px-2.5 py-2 text-left">
                  <MessageSquare className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{s.title}</span>
                    <span className="block text-xs text-muted">
                      {relativeTime(s.updated_at)}, {s.questions} {s.questions === 1 ? "question" : "questions"}
                      {openIds.includes(s.id) && ", open"}
                    </span>
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
      )}
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
  const [view, setView] = useState<"chat" | "history">("chat");

  // Per-tab state, so replies keep streaming and drafts survive while you look at another tab.
  const [drafts, setDrafts] = useState<Record<TabId, string>>({});
  const [pending, setPending] = useState<Record<TabId, ChatTurn[]>>({});
  const [busy, setBusy] = useState<Record<TabId, boolean>>({});
  const aborts = useRef(new Map<TabId, AbortController>());
  const bottom = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const tabRefs = useRef(new Map<TabId, HTMLButtonElement>());

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
    // Block body on purpose: scrollIntoView returns a Promise in newer browsers, and an effect must not return one.
    bottom.current?.scrollIntoView({ block: "end" });
  }, [turns.length, pending, active]);
  useEffect(() => {
    const controllers = aborts.current;
    return () => controllers.forEach((c) => c.abort());
  }, []);
  useEffect(() => {
    if (view === "chat") input.current?.focus();
  }, [active, view]);

  const setDraft = (id: TabId, text: string) => setDrafts((d) => ({ ...d, [id]: text }));

  function newChat() {
    setView("chat");
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
      // Keep a failed reply visible (errors are not saved); otherwise show the saved transcript.
      setPending((p) => ({ ...p, [id]: reply.error ? (p[id] ?? []) : [] }));
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
    <aside aria-label="Assistant" className="flex h-full flex-col bg-panel">
      <header className="border-b border-line">
        <div className="flex items-center gap-1 px-4 pt-3 pb-2">
          <div className="min-w-0 flex-1">
            <h2 className="flex items-center gap-1.5 font-semibold">
              <Sparkles className="size-4 text-muted" aria-hidden /> Assistant
            </h2>
            <p className="truncate text-xs text-muted">
              {appName}, {run.review_count} reviews
            </p>
          </div>
          <button
            onClick={() => setView((v) => (v === "history" ? "chat" : "history"))}
            aria-pressed={view === "history"}
            title="Chat history"
            className={cx(
              "grid size-8 place-items-center rounded-md text-muted hover:bg-soft hover:text-ink",
              view === "history" && "bg-soft text-ink",
            )}
          >
            <History className="size-4" aria-hidden />
            <span className="sr-only">Chat history</span>
          </button>
          <button onClick={newChat} title="New chat" className="grid size-8 place-items-center rounded-md text-muted hover:bg-soft hover:text-ink">
            <SquarePen className="size-4" aria-hidden />
            <span className="sr-only">New chat</span>
          </button>
          <button onClick={onClose} title="Close assistant" className="grid size-8 place-items-center rounded-md text-muted hover:bg-soft hover:text-ink">
            <X className="size-4" aria-hidden />
            <span className="sr-only">Close assistant</span>
          </button>
        </div>

        {view === "chat" ? (
          <div className="flex items-end gap-1 px-3">
            <div role="tablist" aria-label="Open chats" onKeyDown={onTabKey} className="flex min-w-0 flex-1 gap-0.5 overflow-x-auto [scrollbar-width:none]">
              {tabs.open.map((id) => {
                const selected = id === active;
                return (
                  <div
                    key={id}
                    className={cx(
                      "group relative flex max-w-[11rem] shrink-0 items-center rounded-t-md border-x border-t text-sm",
                      selected ? "-mb-px border-line bg-panel" : "border-transparent text-muted hover:bg-soft hover:text-ink",
                    )}
                  >
                    <button
                      ref={(el) => {
                        if (el) tabRefs.current.set(id, el);
                        else tabRefs.current.delete(id);
                      }}
                      role="tab"
                      aria-selected={selected}
                      tabIndex={selected ? 0 : -1}
                      onClick={() => activate(id)}
                      title={titleOf(id)}
                      className="flex min-w-0 items-center gap-1.5 py-2 pr-1 pl-3"
                    >
                      {busy[id] && <Loader2 className="size-3 shrink-0 animate-spin" aria-label="Answering" />}
                      <span className={cx("truncate", selected && "font-medium")}>{titleOf(id)}</span>
                    </button>
                    <button
                      onClick={() => close(id)}
                      aria-label={`Close tab “${titleOf(id)}”`}
                      title="Close tab (the chat stays in history)"
                      className={cx(
                        "mr-1 grid size-5 shrink-0 place-items-center rounded text-muted hover:bg-soft hover:text-ink",
                        !selected && "opacity-0 group-hover:opacity-100 focus:opacity-100",
                      )}
                    >
                      <X className="size-3" aria-hidden />
                    </button>
                  </div>
                );
              })}
            </div>
            <button onClick={newChat} title="New chat" className="mb-1 grid size-7 shrink-0 place-items-center rounded-md text-muted hover:bg-soft hover:text-ink">
              <Plus className="size-4" aria-hidden />
              <span className="sr-only">New chat</span>
            </button>
          </div>
        ) : (
          <p className="px-4 pb-2 text-xs text-muted">All chats about this analysis. Other analyses have their own.</p>
        )}
      </header>

      {view === "history" ? (
        <HistoryView
          runId={run.id}
          sessions={sessions ?? []}
          openIds={tabs.open}
          onOpen={(id) => {
            activate(id);
            setView("chat");
          }}
          onDeleted={close}
        />
      ) : (
        <>
          <div role="tabpanel" aria-label={titleOf(active)} className="min-h-0 flex-1 overflow-y-auto px-4 py-4" aria-live="polite">
            {!isNew(active) && chat.isLoading ? (
              <Loader2 className="size-4 animate-spin text-muted" aria-label="Loading" />
            ) : turns.length === 0 ? (
              <div className="flex flex-col gap-4 pt-2">
                <div>
                  <p className="font-semibold">Ask about {appName}</p>
                  <p className="mt-1 text-sm text-muted">
                    The assistant looks up this analysis of {run.review_count} reviews, then answers with numbers and real
                    quotes. It can't see other analyses or chats.
                  </p>
                </div>
                <div className="flex flex-col gap-2">
                  <p className="text-xs font-medium text-muted">Try asking</p>
                  {list.data?.suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      disabled={!ready || isBusy}
                      className="rounded-lg border border-line px-3 py-2 text-left text-sm hover:border-muted hover:bg-soft disabled:opacity-50"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-6">
                {turns.map((turn, i) =>
                  turn.role === "user" ? (
                    <p key={i} className="ml-8 self-end rounded-2xl rounded-br-md bg-soft px-3.5 py-2 text-sm whitespace-pre-wrap">
                      {turn.text}
                    </p>
                  ) : (
                    <AssistantMessage key={i} turn={turn} index={i} streaming={isBusy && i === turns.length - 1} />
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
              <div className="rounded-xl border border-line bg-paper shadow-sm transition-colors focus-within:border-ink focus-within:ring-2 focus-within:ring-ink/10">
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
                  className="block max-h-48 min-h-12 w-full resize-none bg-transparent px-3.5 pt-3 pb-1 text-[0.95rem] leading-relaxed outline-none [field-sizing:content] placeholder:text-muted focus-visible:outline-none"
                />
                <div className="flex items-center gap-1.5 px-2 pb-2">
                  <span
                    title={`Answers use only the ${run.review_count} reviews in this analysis of ${appName}`}
                    className="inline-flex min-w-0 items-center gap-1 rounded-md bg-soft px-2 py-1 text-xs text-muted"
                  >
                    <ScanSearch className="size-3.5 shrink-0" aria-hidden />
                    <span className="truncate">This analysis only</span>
                  </span>
                  <Link
                    to="/settings"
                    title="Change AI model"
                    className="inline-flex min-w-0 items-center gap-1 rounded-md px-2 py-1 text-xs text-muted hover:bg-soft hover:text-ink"
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
                      className="grid size-8 place-items-center rounded-full bg-ink text-paper transition-opacity hover:opacity-90 disabled:opacity-30"
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
      )}
    </aside>
  );
}
