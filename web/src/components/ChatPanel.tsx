import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowUp, Check, Loader2, Square, Trash2, X } from "lucide-react";
import { chatApi, type ChatEvent, type ChatTurn, type CitedReview, type Run } from "../lib/api";
import { shortDate } from "../lib/format";
import { toLLMConfig, useConnection } from "../lib/settings";
import { Notice, Stars, cx } from "./ui";

const CITATION = /\[\[r:([^\]\s]+)\]\]/g;

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

export function ChatPanel({ run, onClose }: { run: Run; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { connection, ready, provider, modelLabel } = useConnection();
  const chat = useQuery({ queryKey: ["chat", run.id], queryFn: () => chatApi.get(run.id) });
  const [pending, setPending] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);

  const turns = [...(chat.data?.turns ?? []), ...pending];
  useEffect(() => {
    // Block body on purpose: scrollIntoView returns a Promise in newer browsers, and an effect must not return one.
    bottom.current?.scrollIntoView({ block: "end" });
  }, [turns.length, pending]);
  useEffect(() => () => abort.current?.abort(), []);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy || !connection) return;
    setDraft("");
    setBusy(true);
    const controller = new AbortController();
    abort.current = controller;
    let reply: AssistantTurn = { role: "assistant", text: "", steps: [], reviews: {} };
    setPending([{ role: "user", text: message }, reply]);
    try {
      for await (const event of chatApi.send(run.id, message, toLLMConfig(connection), controller.signal)) {
        reply = applyEvent(reply, event);
        setPending([{ role: "user", text: message }, reply]);
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        reply = { ...reply, error: error instanceof Error ? error.message : String(error) };
        setPending([{ role: "user", text: message }, reply]);
      }
    } finally {
      setBusy(false);
      abort.current = null;
      await queryClient.invalidateQueries({ queryKey: ["chat", run.id] });
      // Keep a failed reply visible (errors are not saved); otherwise show the saved transcript.
      setPending((current) => (reply.error ? current : []));
      input.current?.focus();
    }
  }

  async function clear() {
    if (!window.confirm("Clear this conversation?")) return;
    await chatApi.clear(run.id);
    setPending([]);
    queryClient.invalidateQueries({ queryKey: ["chat", run.id] });
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send(draft);
    }
  };

  return (
    <aside aria-label="Assistant" className="flex h-full flex-col bg-panel">
      <header className="flex items-center gap-2 border-b border-line px-4 py-3">
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold">Ask about {run.app.title ?? "this app"}</h2>
          <p className="truncate text-xs text-muted">
            {!ready ? (
              "No AI model connected"
            ) : provider?.id === "chatgpt" ? (
              <>
                Using ChatGPT plan.{" "}
                <a href="https://chatgpt.com/#settings" target="_blank" rel="noreferrer" className="underline underline-offset-2">
                  Manage usage
                </a>
              </>
            ) : (
              `${provider?.name} ${modelLabel}. Answers cite the reviews they use.`
            )}
          </p>
        </div>
        {turns.length > 0 && (
          <button onClick={clear} disabled={busy} aria-label="Clear conversation" className="rounded p-1.5 text-muted hover:bg-soft hover:text-ink disabled:opacity-40">
            <Trash2 className="size-4" />
          </button>
        )}
        <button onClick={onClose} aria-label="Close assistant" className="rounded p-1.5 text-muted hover:bg-soft hover:text-ink">
          <X className="size-4" />
        </button>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4" aria-live="polite">
        {chat.isLoading ? (
          <Loader2 className="size-4 animate-spin text-muted" aria-label="Loading" />
        ) : turns.length === 0 ? (
          <div className="flex flex-col gap-4">
            <p className="text-sm text-muted">
              Ask anything about these {run.review_count} reviews. The assistant looks up the analysis, then answers with
              numbers and real quotes.
            </p>
            <div className="flex flex-col gap-2">
              {chat.data?.suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  disabled={!ready || busy}
                  className="rounded-md border border-line px-3 py-2 text-left text-sm hover:bg-soft disabled:opacity-50"
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
                <p key={i} className="ml-8 self-end whitespace-pre-wrap rounded-lg bg-soft px-3 py-2 text-sm">
                  {turn.text}
                </p>
              ) : (
                <AssistantMessage key={i} turn={turn} index={i} streaming={busy && i === turns.length - 1} />
              ),
            )}
          </div>
        )}
        <div ref={bottom} />
      </div>

      <form
        className="border-t border-line p-3"
        onSubmit={(e) => {
          e.preventDefault();
          send(draft);
        }}
      >
        {!ready ? (
          <p className="px-1 py-2 text-sm text-muted">
            <Link to="/settings" className="font-medium text-ink underline underline-offset-2">
              Connect an AI model
            </Link>{" "}
            to ask questions.
          </p>
        ) : (
          <div className="flex items-end gap-2 rounded-lg border border-line bg-paper p-2 focus-within:border-ink">
            <label htmlFor="chat-input" className="sr-only">
              Your question
            </label>
            <textarea
              id="chat-input"
              ref={input}
              rows={1}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Ask a question"
              className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-1 py-1.5 text-sm outline-none [field-sizing:content] placeholder:text-muted"
            />
            {busy ? (
              <button
                type="button"
                onClick={() => abort.current?.abort()}
                aria-label="Stop answering"
                className="grid size-9 place-items-center rounded-md bg-ink text-paper"
              >
                <Square className="size-3.5 fill-current" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!draft.trim()}
                aria-label="Send"
                className={cx("grid size-9 place-items-center rounded-md bg-ink text-paper", !draft.trim() && "opacity-40")}
              >
                <ArrowUp className="size-4" />
              </button>
            )}
          </div>
        )}
      </form>
    </aside>
  );
}
