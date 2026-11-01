const numberFormat = new Intl.NumberFormat("en");
const compactFormat = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });

export const num = (value: number | null | undefined) => (value == null ? "–" : numberFormat.format(value));
export const compact = (value: number | null | undefined) => (value == null ? "–" : compactFormat.format(value));
export const pct = (share: number | null | undefined, digits = 0) =>
  share == null ? "–" : `${(share * 100).toFixed(digits)}%`;
export const rating = (value: number | null | undefined) => (value == null ? "–" : value.toFixed(2));
export const plural = (count: number, word: string, many = `${word}s`) => `${num(count)} ${count === 1 ? word : many}`;

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleDateString("en", { day: "numeric", month: "short", year: "numeric" });
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31_536_000], ["month", 2_592_000], ["week", 604_800], ["day", 86_400], ["hour", 3_600], ["minute", 60],
  ];
  const format = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return format.format(-Math.round(seconds / size), unit);
  }
  return "just now";
}

export function duration(seconds: number): string {
  if (seconds < 60) return `${Math.max(5, Math.round(seconds / 5) * 5)} seconds`;
  const minutes = Math.round(seconds / 60);
  return minutes === 1 ? "about a minute" : `about ${minutes} minutes`;
}

export function flag(country: string | null | undefined): string {
  if (!country || country.length !== 2) return "";
  return String.fromCodePoint(...[...country.toUpperCase()].map((c) => 127397 + c.charCodeAt(0)));
}

const LABELS: Record<string, string> = {
  // feedback types
  bug: "Bug",
  feature_request: "Feature request",
  ux_friction: "UX friction",
  complaint: "Complaint",
  praise: "Praise",
  question: "Question",
  other: "Other",
  // journey stages
  install_onboarding: "Install & onboarding",
  account_login: "Account & login",
  core_experience: "Core experience",
  search_navigation: "Search & navigation",
  payments_subscription: "Payments & subscription",
  notifications: "Notifications",
  settings_privacy: "Settings & privacy",
  support_help: "Support & help",
  app_updates: "App updates",
  // emotions
  frustration: "Frustration",
  anger: "Anger",
  confusion: "Confusion",
  disappointment: "Disappointment",
  neutral: "Neutral",
  satisfaction: "Satisfaction",
  delight: "Delight",
  // sentiment
  negative: "Negative",
  positive: "Positive",
  unknown: "Not analyzed",
};

export const label = (value: string | null | undefined) =>
  value ? (LABELS[value] ?? value.charAt(0).toUpperCase() + value.slice(1).replaceAll("_", " ")) : "Not analyzed";

export const STAGES: { id: string; label: string }[] = [
  { id: "fetching_app", label: "Look up the app" },
  { id: "fetching_reviews", label: "Download reviews" },
  { id: "analyzing", label: "Analyze with AI" },
  { id: "grouping_themes", label: "Group themes" },
];

export function ratingFilterLabel(ratings: number[] | null): string {
  if (!ratings || ratings.length === 0 || ratings.length === 5) return "All ratings";
  if (ratings.join() === "1,2") return "Negative (1–2★)";
  if (ratings.join() === "1,2,3") return "Critical (1–3★)";
  return `${ratings.join(", ")}★ only`;
}
