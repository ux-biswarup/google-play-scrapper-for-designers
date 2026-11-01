import { useState } from "react";
import { Link } from "react-router";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Copy, Sparkles } from "lucide-react";
import { viewsApi, type Review, type Run } from "../../lib/api";
import { num, pct, rating } from "../../lib/format";
import { toLLMConfig, useConnection } from "../../lib/settings";
import { Button, Notice, Panel, Spinner, Stars } from "../../components/ui";
import { Quote } from "./Problems";
import { SectionIntro, ShareBar, ThemeLink } from "./shared";

function ReplyDraft({ run, review }: { run: Run; review: Review }) {
  const { connection, ready } = useConnection();
  const [text, setText] = useState("");
  const [copied, setCopied] = useState(false);
  const draft = useMutation({
    mutationFn: () => viewsApi.draftReply(run.id, review.review_id, toLLMConfig(connection!)),
    onSuccess: (d) => setText(d.reply),
  });
  const limit = draft.data?.limit ?? 350;
  if (!ready) return null;
  if (!draft.data && !draft.isPending && !draft.isError)
    return (
      <Button size="sm" variant="ghost" className="self-start" onClick={() => draft.mutate()}>
        <Sparkles className="size-4" aria-hidden /> Draft a reply
      </Button>
    );
  if (draft.isPending) return <Spinner label="Drafting a reply" />;
  if (draft.isError) return <Notice tone="error" title="Couldn't draft a reply">{draft.error.message}</Notice>;
  const id = `reply-${review.review_id}`;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs text-muted">
        Draft reply. Edit before posting it in Play Console.
      </label>
      <textarea
        id={id}
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        className="w-full rounded-md border border-line bg-panel px-3 py-2 text-sm focus:border-ink focus:outline-none"
      />
      <div className="flex items-center justify-between gap-3">
        <span className={text.length > limit ? "text-xs text-neg" : "text-xs text-muted"}>
          {text.length} / {limit} characters
        </span>
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" onClick={() => draft.mutate()}>
            Try again
          </Button>
          <Button
            size="sm"
            onClick={async () => {
              await navigator.clipboard.writeText(text);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            }}
          >
            {copied ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}
            {copied ? "Copied" : "Copy"}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function RepliesTab({ run }: { run: Run }) {
  const data = useQuery({ queryKey: ["view-replies", run.id], queryFn: () => viewsApi.replies(run.id) });
  const { ready } = useConnection();
  if (data.isLoading) return <Spinner />;
  if (data.error) return <Notice tone="error" title="Couldn't load replies">{data.error.message}</Notice>;
  const d = data.data!;

  return (
    <div className="flex flex-col gap-6">
      <SectionIntro title="Developer replies">
        How the team answers reviews: which complaints get a reply, which are left unanswered, and whether replies
        read as copy-paste. Answering the most-seen complaints shows every visitor to the store page that you listen.
      </SectionIntro>

      <Panel>
        <dl className="flex flex-wrap gap-x-10 gap-y-3">
          <div>
            <dt className="text-sm text-muted">Reviews with a reply</dt>
            <dd className="text-2xl font-semibold tabular-nums">{pct(d.reply_rate)}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted">1–2★ reviews with a reply</dt>
            <dd className="text-2xl font-semibold tabular-nums">
              {d.negative_reply_rate == null ? "–" : pct(d.negative_reply_rate)}
              <span className="ml-1.5 text-sm font-normal text-muted">of {num(d.negative)}</span>
            </dd>
          </div>
          {d.templated_share != null && (
            <div>
              <dt className="text-sm text-muted">Replies that are copy-paste</dt>
              <dd className="text-2xl font-semibold tabular-nums">{pct(d.templated_share)}</dd>
            </div>
          )}
          {d.avg_rating_replied != null && (
            <div>
              <dt className="text-sm text-muted">Rating of replied reviews</dt>
              <dd className="text-2xl font-semibold tabular-nums">
                {rating(d.avg_rating_replied)}
                <span className="ml-1.5 text-sm font-normal text-muted">vs {rating(d.avg_rating_not_replied)} not replied</span>
              </dd>
            </div>
          )}
        </dl>
        {d.avg_rating_replied != null && d.avg_rating_not_replied != null && (
          <p className="mt-3 text-xs text-muted">
            Teams mostly answer complaints, so replied reviews have lower ratings. That compares different reviews; it
            doesn't show that replying lowers ratings.
          </p>
        )}
        {d.replied === 0 && (
          <p className="mt-3 text-sm text-muted">
            The team hasn't replied to any of these reviews. Google Play shows replies under the review, so even a few
            answers to the most-seen complaints are visible to everyone deciding whether to install.
          </p>
        )}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Reply rate by rating">
          <ul className="flex flex-col gap-3 text-sm">
            {d.by_rating.map((b) => (
              <li key={b.rating} className="grid grid-cols-[5.5rem_minmax(0,1fr)_3rem] items-center gap-3">
                <Stars value={b.rating} />
                <ShareBar value={b.reply_rate} tone={b.rating <= 2 ? "neg" : "muted"} label={`${pct(b.reply_rate)} of ${b.rating}-star reviews replied`} />
                <span className="text-right tabular-nums text-muted">{pct(b.reply_rate)}</span>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="Complaints left unanswered">
          {d.unanswered_themes.length === 0 ? (
            <p className="text-sm text-muted">Every 1–2★ review has a reply.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted">
                  <th className="pb-1.5 font-normal">Theme</th>
                  <th className="pb-1.5 text-right font-normal">Reviews</th>
                  <th className="pb-1.5 text-right font-normal">Helpful votes</th>
                </tr>
              </thead>
              <tbody>
                {d.unanswered_themes.map((t) => (
                  <tr key={t.theme} className="border-t border-line">
                    <th scope="row" className="py-1.5 pr-3 text-left font-normal">
                      <span className="highlight">
                        <ThemeLink theme={t.theme} />
                      </span>
                    </th>
                    <td className="py-1.5 text-right tabular-nums">{t.reviews}</td>
                    <td className="py-1.5 text-right tabular-nums text-muted">{num(t.helpful_votes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      {d.reply_first.length > 0 && (
        <Panel title="Reply to these first">
          <p className="-mt-1 mb-4 text-sm text-muted">
            Unanswered 1–2★ reviews that most people found helpful, so the most people see them.
            {!ready && (
              <>
                {" "}
                <Link to="/settings" className="font-medium text-ink underline underline-offset-2">
                  Connect an AI model
                </Link>{" "}
                to draft replies.
              </>
            )}
          </p>
          <ul className="flex flex-col gap-6">
            {d.reply_first.map((r) => (
              <li key={r.review_id} className="flex flex-col gap-2">
                <Quote review={r} />
                <ReplyDraft run={run} review={r} />
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {d.templates.length > 0 && (
        <Panel title="Copy-paste replies">
          <p className="-mt-1 mb-3 text-sm text-muted">
            The same text sent to several reviews. Users notice templates; answering the specific problem reads as
            listening.
          </p>
          <ul className="flex flex-col gap-3">
            {d.templates.map((t) => (
              <li key={t.text} className="flex items-start justify-between gap-4 rounded-md bg-soft px-3 py-2 text-sm">
                <span>{t.text}</span>
                <span className="shrink-0 tabular-nums text-muted">{t.uses}×</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      {d.examples.length > 0 && (
        <Panel title="How the team replies to complaints">
          <ul className="flex flex-col gap-5">
            {d.examples.map((r) => (
              <li key={r.review_id} className="flex flex-col gap-2">
                <Quote review={r} clamp />
                <p className="ml-4 rounded-md bg-soft px-3 py-2 text-sm">
                  <span className="font-medium">Reply: </span>
                  <span className="text-muted">{r.reply}</span>
                </p>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}
