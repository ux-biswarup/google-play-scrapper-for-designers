import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pin as PinIcon } from "lucide-react";
import { pinsApi, type Pin } from "../lib/api";
import { cx } from "./ui";

type PinState = { pins: Pin[]; pinned: Set<string>; toggle: (reviewId: string) => void; busy: boolean };
const PinContext = createContext<PinState | null>(null);

/** Pins for one analysis. Quotes inside get a pin button; outside (e.g. Benchmark) they don't. */
export function PinProvider({ runId, children }: { runId: string; children: ReactNode }) {
  const queryClient = useQueryClient();
  const key = ["pins", runId];
  const pins = useQuery({ queryKey: key, queryFn: () => pinsApi.list(runId) });
  const toggle = useMutation({
    mutationFn: async (reviewId: string) => {
      const isPinned = (queryClient.getQueryData<Pin[]>(key) ?? []).some((p) => p.review_id === reviewId);
      if (isPinned) {
        await pinsApi.unpin(runId, reviewId);
        return (queryClient.getQueryData<Pin[]>(key) ?? []).filter((p) => p.review_id !== reviewId);
      }
      return pinsApi.pin(runId, reviewId);
    },
    onSuccess: (next) => queryClient.setQueryData(key, next),
  });
  const value = useMemo<PinState>(() => {
    const list = pins.data ?? [];
    return { pins: list, pinned: new Set(list.map((p) => p.review_id)), toggle: toggle.mutate, busy: toggle.isPending };
  }, [pins.data, toggle.mutate, toggle.isPending]);
  return <PinContext.Provider value={value}>{children}</PinContext.Provider>;
}

export const usePins = () => useContext(PinContext);

export function PinButton({ reviewId }: { reviewId: string }) {
  const pins = usePins();
  if (!pins) return null;
  const on = pins.pinned.has(reviewId);
  return (
    <button
      type="button"
      onClick={() => pins.toggle(reviewId)}
      disabled={pins.busy}
      aria-pressed={on}
      title={on ? "Unpin" : "Pin as evidence for the report"}
      className={cx(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs transition-colors disabled:opacity-60 print:hidden",
        on ? "bg-soft font-medium text-ink" : "text-muted hover:bg-soft hover:text-ink",
      )}
    >
      <PinIcon className={cx("size-3", on && "fill-current")} aria-hidden />
      {on ? "Pinned" : "Pin"}
    </button>
  );
}
