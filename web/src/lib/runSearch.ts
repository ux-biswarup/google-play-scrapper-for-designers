import type { Run } from "./api";
import { countryName } from "./locales";

/** Lowercase without accents, so "pokemon" finds "Pokémon". */
export const fold = (text: string) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

const STATUS_WORDS: Record<Run["status"], string> = {
  queued: "analyzing running in progress",
  running: "analyzing running in progress",
  completed: "completed done",
  failed: "failed error",
  cancelled: "cancelled canceled stopped",
};

function haystack(run: Run): string {
  return fold(
    [
      run.app.title,
      run.app.developer,
      run.app.store_id,
      run.country,
      run.country ? countryName(run.country) : "",
      run.provider,
      run.model,
      STATUS_WORDS[run.status],
    ]
      .filter(Boolean)
      .join(" "),
  );
}

/** Runs matching every word of the query, in their original order. */
export function searchRuns(runs: Run[], query: string): Run[] {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return runs;
  return runs.filter((run) => {
    const text = haystack(run);
    return words.every((w) => text.includes(w));
  });
}

/** Splits text into [plain, match, plain, ...] parts for highlighting the query words (accent-insensitive). */
export function highlightParts(text: string, query: string): { text: string; match: boolean }[] {
  const words = fold(query).split(/\s+/).filter(Boolean);
  const chars = [...text];
  const folded = chars.map((c) => fold(c));
  // Only highlight when each character folds to one character, so positions line up with the original.
  if (words.length === 0 || folded.some((f) => f.length !== 1)) return [{ text, match: false }];
  const lower = folded.join("");
  const hit = new Array(chars.length).fill(false);
  for (const w of words) {
    for (let i = lower.indexOf(w); i !== -1; i = lower.indexOf(w, i + 1)) hit.fill(true, i, i + w.length);
  }
  const parts: { text: string; match: boolean }[] = [];
  chars.forEach((c, i) => {
    const last = parts[parts.length - 1];
    if (last && last.match === hit[i]) last.text += c;
    else parts.push({ text: c, match: hit[i] });
  });
  return parts;
}
