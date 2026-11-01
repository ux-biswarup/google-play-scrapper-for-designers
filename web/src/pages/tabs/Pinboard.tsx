import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Pin as PinIcon } from "lucide-react";
import { pinsApi, type Pin, type Run } from "../../lib/api";
import { shortDate } from "../../lib/format";
import { usePins } from "../../components/pins";
import { Button, EmptyState, Spinner } from "../../components/ui";
import { Quote } from "./Problems";
import { SectionIntro } from "./shared";

function toMarkdown(pins: Pin[]): string {
  return pins
    .map((p) => {
      const quote = `> “${p.content.split(/\s+/).join(" ")}” (${p.rating}★, ${shortDate(p.date)})`;
      return p.note ? `${quote}\n\nNote: ${p.note}` : quote;
    })
    .join("\n\n");
}

function NoteField({ run, pin }: { run: Run; pin: Pin }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState(pin.note);
  const save = useMutation({
    mutationFn: () => pinsApi.pin(run.id, pin.review_id, note),
    onSuccess: (next) => queryClient.setQueryData(["pins", run.id], next),
  });
  const id = `note-${pin.review_id}`;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-xs text-muted">
        Why it matters (optional)
      </label>
      <textarea
        id={id}
        value={note}
        rows={2}
        maxLength={1000}
        onChange={(e) => setNote(e.target.value)}
        onBlur={() => note !== pin.note && save.mutate()}
        placeholder="e.g. Shows the login loop after the 2.0 update"
        className="w-full rounded-md border border-line bg-panel px-3 py-2 text-sm placeholder:text-muted focus:border-ink focus:outline-none"
      />
      {save.isSuccess && note === pin.note && <span className="text-xs text-muted">Saved</span>}
    </div>
  );
}

export function PinboardTab({ run }: { run: Run }) {
  const pins = usePins();
  const [copied, setCopied] = useState(false);
  if (!pins) return <Spinner />;
  const copy = async () => {
    await navigator.clipboard.writeText(toMarkdown(pins.pins));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="flex flex-col gap-6">
      <SectionIntro title="Pinned quotes">
        Your evidence wall. Pin quotes from any view while you explore, add why each one matters, and use them in
        decks, tickets and design reviews. They're added to the research report when you download it.
      </SectionIntro>
      {pins.pins.length === 0 ? (
        <EmptyState title="Nothing pinned yet">
          Look for <PinIcon className="inline size-3.5" aria-label="the pin button" /> Pin under any quote, for example in
          Problems, Journey map or Reviews.
        </EmptyState>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <Button size="sm" onClick={copy}>
              {copied ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />}
              {copied ? "Copied" : "Copy as Markdown"}
            </Button>
            <span className="text-sm text-muted">{pins.pins.length} pinned</span>
          </div>
          <ul className="flex flex-col gap-6">
            {pins.pins.map((p) => (
              <li key={p.review_id} className="flex flex-col gap-3 rounded-lg border border-line bg-panel p-4">
                <Quote review={p} />
                <NoteField run={run} pin={p} />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
