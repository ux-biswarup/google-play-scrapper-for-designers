// Typed client for the FastAPI backend (served under /api).

export type Provider = {
  id: string;
  name: string;
  kind: "anthropic" | "openai";
  base_url: string | null;
  requires_key: boolean;
  key_url: string | null;
  requires_base_url: boolean;
  env_var: string | null;
  has_env_key: boolean;
  default_model: string | null;
  /** ChatGPT plan only: signed in with plan usage granted. */
  connected: boolean | null;
  /** A key saved in the encrypted vault (only a masked hint is ever sent). */
  saved_key: SavedKey | null;
};

export type SavedKey = { name: string; hint: string; storage: "saved" | "session"; saved_at: number };

export type LLMConfig = { provider: string; model?: string; api_key?: string; base_url?: string };

export type AppInfo = {
  id: number;
  platform: string;
  store_id: string;
  title: string | null;
  developer: string | null;
  icon_url: string | null;
  genre: string | null;
  score: number | null;
  ratings_count: number | null;
  installs: string | null;
  version: string | null;
  store_url: string | null;
};

export type AppSearchHit = {
  store_id: string;
  title: string | null;
  developer: string | null;
  icon_url: string | null;
  score: number | null;
};

export type AppDetails = AppSearchHit & {
  genre: string | null;
  ratings_count: number | null;
  installs: string | null;
  version: string | null;
  store_url: string | null;
  summary: string | null;
};

export type RunStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export type Run = {
  id: string;
  status: RunStatus;
  stage: string | null;
  progress_done: number;
  progress_total: number;
  message: string | null;
  error: string | null;
  country: string | null;
  lang: string | null;
  ratings: number[] | null;
  requested_count: number;
  date_from: string | null;
  date_to: string | null;
  sampling: "newest" | "spread";
  output_language: string;
  provider: string;
  model: string;
  /** 1: original tags; 2+: severity, user type, churn risk, competitors, accessibility. */
  tag_version: number;
  review_count: number;
  tagged_count: number;
  failed_count: number;
  input_tokens: number;
  output_tokens: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  app: AppInfo;
};

export type RunCreate = {
  app: string;
  country: string;
  lang: string;
  count: number;
  ratings: number[] | null;
  output_language: string;
  llm: LLMConfig;
  date_from?: string | null;
  date_to?: string | null;
  sampling?: "newest" | "spread";
};

export type ReviewWindow = {
  in_range: number;
  complete: boolean;
  scanned: number;
  max_scan: number;
  oldest_reached: string | null;
  first_review: string | null;
  last_review: string | null;
};

export type Estimate = { reviews: number; ai_requests: number; input_tokens: number; output_tokens: number; seconds: number };

export type Share = { value: string; share: number };

export type Review = {
  review_id: string;
  date: string | null;
  rating: number;
  sentiment: "negative" | "neutral" | "positive";
  content: string;
  app_version: string;
  thumbs_up: number;
  reply: string | null;
  category: string | null;
  themes: string[];
  journey_stage: string | null;
  emotion: string | null;
};

export type Overview = {
  run: Run;
  app: AppInfo;
  kpis: {
    review_count: number;
    avg_rating: number | null;
    negative_share: number | null;
    positive_share: number | null;
    analyzed_share: number | null;
    date_from: string | null;
    date_to: string | null;
  };
  rating_distribution: { rating: number; review_count: number }[];
  sentiment_distribution: { sentiment: string; review_count: number }[];
  category_distribution: { category: string; review_count: number }[];
  journey_distribution: { journey_stage: string; review_count: number }[];
  emotion_distribution: { emotion: string; review_count: number }[];
};

export type Theme = {
  theme: string;
  mentions: number;
  reach: number;
  avg_rating: number;
  negative_share: number;
  positive_share: number;
  trend: "rising" | "falling" | "steady";
  growth: number;
  impact: number;
  categories: Share[];
  journey_stages: Share[];
  emotions: Share[];
  versions: Share[];
  first_seen: string | null;
  last_seen: string | null;
  quotes: Review[];
};

export type ThemeBoard = { total_reviews: number; problems: Theme[]; strengths: Theme[]; formula: string };

export type SeriesPoint = {
  date: string;
  review_count: number;
  avg_rating: number;
  negative_share: number;
  neutral_share: number;
  positive_share: number;
};

export type Trends = {
  grain: Grain;
  series: SeriesPoint[];
  spikes: {
    series: { date: string; one_star: number; total: number; baseline: number; is_spike: boolean }[];
    spikes: { date: string; one_star: number; baseline: number; score: number; top_themes: string[]; versions: string[] }[];
  };
  trending_themes: { theme: string; current: number; previous: number; change: number; direction: "up" | "down" | "flat" }[];
  versions: {
    app_version: string;
    review_count: number;
    avg_rating: number;
    negative_share: number;
    first_seen: string;
    last_seen: string;
  }[];
};

export type Grain = "day" | "week" | "month";

export type ThemeShift = {
  theme: string;
  before_count: number;
  after_count: number;
  before_share: number;
  after_share: number;
  delta: number;
};

export type GroupSummary = {
  review_count: number;
  avg_rating: number | null;
  negative_share: number | null;
  positive_share: number | null;
  top_themes: { theme: string; count: number; share: number }[];
};

export type Comparison = {
  mode: "version" | "date";
  pivot: string;
  split_date: string;
  before: GroupSummary;
  after: GroupSummary;
  delta_avg_rating: number | null;
  delta_negative_share: number | null;
  new_themes: ThemeShift[];
  rising_themes: ThemeShift[];
  falling_themes: ThemeShift[];
};

export type ReviewPage = { total: number; page: number; page_size: number; items: Review[] };

export type ReviewQuery = {
  q?: string;
  rating?: number[];
  category?: string;
  theme?: string;
  journey_stage?: string;
  emotion?: string;
  app_version?: string;
  sort?: string;
  page?: number;
  page_size?: number;
};

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) detail = body.detail[0].msg;
    } catch {
      // keep the generic message
    }
    throw new ApiError(detail, res.status);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

function query(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => search.append(key, String(v)));
    else search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

const post = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const api = {
  providers: () => request<Provider[]>("/providers"),
  models: (config: LLMConfig) => request<{ models: { id: string; name: string }[] }>("/providers/models", post(config)),
  testConnection: (config: LLMConfig) => request<{ ok: boolean; latency_ms: number }>("/providers/test", post(config)),

  searchApps: (q: string, country: string, lang: string) =>
    request<AppSearchHit[]>(`/apps/search${query({ q, country, lang, limit: 8 })}`),
  lookupApp: (id: string, country: string, lang: string) =>
    request<AppDetails>(`/apps/lookup${query({ id, country, lang })}`),

  estimate: (count: number) => request<Estimate>("/runs/estimate", post({ count: Math.max(10, count) })),
  reviewWindow: (body: { app: string; country: string; lang: string; ratings: number[] | null; date_from: string; date_to: string }) =>
    request<ReviewWindow>("/apps/review-window", post(body)),
  createRun: (body: RunCreate) => request<Run>("/runs", post(body)),
  runs: () => request<Run[]>("/runs"),
  run: (id: string) => request<Run>(`/runs/${id}`),
  cancelRun: (id: string) => request<{ status: string }>(`/runs/${id}/cancel`, { method: "POST" }),
  deleteRun: (id: string) => request<void>(`/runs/${id}`, { method: "DELETE" }),
  runEventsUrl: (id: string) => `/api/runs/${id}/events`,

  overview: (id: string) => request<Overview>(`/runs/${id}/overview`),
  themes: (id: string) => request<ThemeBoard>(`/runs/${id}/themes${query({ limit: 30, quotes: 3 })}`),
  trends: (id: string, grain: Grain) => request<Trends>(`/runs/${id}/trends${query({ grain })}`),
  compare: (id: string, mode: "version" | "date", pivot: string) =>
    request<Comparison>(`/runs/${id}/compare${query({ mode, pivot })}`),
  reviews: (id: string, params: ReviewQuery) => request<ReviewPage>(`/runs/${id}/reviews${query(params)}`),
  chartUrl: (id: string, chart: string, fmt: "png" | "svg" = "png") => `/api/runs/${id}/charts/${chart}.${fmt}`,
};

// ---- Assistant chat ---------------------------------------------------------------------------

/** A review as returned by the assistant's tools (used for citations). */
export type CitedReview = {
  review_id: string;
  rating: number;
  date: string;
  app_version: string;
  helpful_votes: number;
  text: string;
  themes: string[];
};

export type ChatStep = { id: string; label: string; ok: boolean; running?: boolean };

export type ChatTurn =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; steps: ChatStep[]; reviews: Record<string, CitedReview>; error?: string };

export type ChatEvent =
  | { type: "text"; delta: string }
  | { type: "tool"; id: string; name: string; label: string }
  | { type: "tool_result"; id: string; ok: boolean; reviews: Record<string, CitedReview> }
  | { type: "error"; message: string }
  | { type: "done"; usage: { input_tokens: number; output_tokens: number } };

/** A starter question written from this analysis, with a short tag saying why (e.g. "Top problem"). */
export type ChatSuggestion = { text: string; tag: string };

/** One conversation about one analysis. Chats never share context with each other or other analyses. */
export type ChatSession = { id: string; title: string; questions: number; created_at: string; updated_at: string };

export const chatApi = {
  sessions: (runId: string, q?: string) =>
    request<{ sessions: (ChatSession & { snippet?: string | null })[]; suggestions: ChatSuggestion[] }>(
      `/runs/${runId}/chat/sessions${query({ q })}`,
    ),
  create: (runId: string) => request<ChatSession>(`/runs/${runId}/chat/sessions`, { method: "POST" }),
  get: (runId: string, sessionId: string) =>
    request<ChatSession & { turns: ChatTurn[] }>(`/runs/${runId}/chat/sessions/${sessionId}`),
  rename: (runId: string, sessionId: string, title: string) =>
    request<ChatSession>(`/runs/${runId}/chat/sessions/${sessionId}`, { method: "PATCH", body: JSON.stringify({ title }) }),
  remove: (runId: string, sessionId: string) =>
    request<void>(`/runs/${runId}/chat/sessions/${sessionId}`, { method: "DELETE" }),

  /** Send a message to one chat and yield the streamed reply events. */
  async *send(runId: string, sessionId: string, message: string, llm: LLMConfig, signal: AbortSignal): AsyncGenerator<ChatEvent> {
    const res = await fetch(`/api/runs/${runId}/chat/sessions/${sessionId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, llm }),
      signal,
    });
    if (!res.ok || !res.body) {
      let detail = `Request failed (${res.status})`;
      try {
        const body = await res.json();
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        // keep the generic message
      }
      throw new ApiError(detail, res.status);
    }
    const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";
      for (const frame of frames) {
        if (frame.startsWith("data: ")) yield JSON.parse(frame.slice(6)) as ChatEvent;
      }
    }
  },
};

// ---- Connecting other AI apps (MCP) -----------------------------------------------------------

export type McpInfo = {
  server_name: string;
  http_url: string;
  python: string;
  project_dir: string;
  module: string;
  tools: { name: string; description: string }[];
};

export const connectApi = { mcp: () => request<McpInfo>("/connect/mcp") };

// ---- Sign-in options --------------------------------------------------------------------------

export type ChatGPTStatus = { signed_in: boolean; email: string | null; plan_usage: boolean };

export const authApi = {
  chatgptStatus: () => request<ChatGPTStatus>("/auth/chatgpt"),
  chatgptStart: (returnTo: string) => request<{ url: string }>("/auth/chatgpt/start", post({ return_to: returnTo })),
  chatgptSignOut: () => request<{ revoked: boolean }>("/auth/chatgpt/signout", { method: "POST" }),
  /** The backend stores the new key in its vault; only a hint comes back. */
  openrouterExchange: (code: string, codeVerifier: string, remember: boolean) =>
    request<SavedKey>("/auth/openrouter/exchange", post({ code, code_verifier: codeVerifier, remember })),
};

// ---- Decision views ---------------------------------------------------------------------------

export type Count = { value: string; count: number; share: number };
export type ReviewLite = Review;

export type BoardItem = {
  theme: string;
  mentions: number;
  helpful_votes: number;
  avg_rating: number;
  high_severity_share: number | null;
  trend: "rising" | "falling" | "steady";
  versions: Count[];
  first_seen: string | null;
  quotes: Review[];
};
export type Board = { count: number; share: number; trend: string; severity: Count[]; items: BoardItem[] };
export type FeedbackBoards = {
  total_tagged: number;
  has_severity: boolean;
  boards: Record<"bug" | "feature_request" | "ux_friction" | "complaint", Board>;
};

export type JourneyStage = {
  stage: string;
  reviews: number;
  share: number;
  avg_rating: number;
  negative_share: number;
  pain: number;
  emotions: Count[];
  problems: { theme: string; mentions: number; negative_share: number }[];
  praise: { theme: string; mentions: number; negative_share: number }[];
  quote: Review | null;
};
export type JourneyMap = { total_tagged: number; worst_stage: string | null; stages: JourneyStage[] };

export type EmotionsView = {
  distribution: Count[];
  matrix: { theme: string; counts: Record<string, number> }[];
  grain: Grain;
  series: ({ date: string; total: number } & Record<string, number | string>)[];
  meaning: Record<string, string>;
  quotes: Record<string, Review[]>;
};

export type Segment = {
  value: string;
  reviews: number;
  share: number;
  avg_rating: number;
  negative_share: number;
  feedback_types: Count[];
  top_themes: { theme: string; mentions: number; share: number }[];
  distinctive_themes: { theme: string; mentions: number; lift: number }[];
  quote: Review | null;
};
export type SegmentsView = {
  by: string;
  label: string;
  available: { id: string; label: string; needs_reanalysis: boolean }[];
  needs_reanalysis: boolean;
  segments: Segment[];
};

export type RisksView = {
  available: boolean;
  total_tagged: number;
  churn: {
    left: number;
    considering: number;
    share: number;
    trend: string;
    themes: { theme: string; mentions: number }[];
    by_user_type: Count[];
    quotes: Review[];
  };
  competitors: { name: string; mentions: number; avg_rating: number; switching: number; quote: Review | null }[];
  payments: { count: number; share: number; themes: { theme: string; mentions: number }[]; quotes: Review[] };
};

export const viewsApi = {
  feedback: (id: string) => request<FeedbackBoards>(`/runs/${id}/views/feedback`),
  journey: (id: string) => request<JourneyMap>(`/runs/${id}/views/journey`),
  emotions: (id: string) => request<EmotionsView>(`/runs/${id}/views/emotions`),
  segments: (id: string, by: string) => request<SegmentsView>(`/runs/${id}/views/segments${query({ by })}`),
  risks: (id: string) => request<RisksView>(`/runs/${id}/views/risks`),
  accessibility: (id: string) => request<AccessibilityView>(`/runs/${id}/views/accessibility`),
  replies: (id: string) => request<RepliesView>(`/runs/${id}/views/replies`),
  draftReply: (id: string, reviewId: string, llm: LLMConfig) =>
    request<{ review_id: string; reply: string; limit: number }>(`/runs/${id}/views/replies/draft`, post({ review_id: reviewId, llm })),
};

export type AccessibilityView = {
  available: boolean;
  total_tagged: number;
  count: number;
  share: number;
  avg_rating: number | null;
  overall_avg_rating: number | null;
  negative_share: number | null;
  trend: string;
  areas: { area: string; count: number; negative_share: number; check: string; quotes: Review[] }[];
  unmatched: number;
  themes: { theme: string; mentions: number }[];
  stages: { value: string; count: number; share: number }[];
  quotes: Review[];
};

export type RepliesView = {
  total: number;
  replied: number;
  reply_rate: number;
  negative: number;
  negative_reply_rate: number | null;
  avg_rating_replied: number | null;
  avg_rating_not_replied: number | null;
  by_rating: { rating: number; reviews: number; reply_rate: number }[];
  templated_share: number | null;
  templates: { text: string; uses: number }[];
  avg_reply_chars: number | null;
  unanswered_themes: { theme: string; reviews: number; helpful_votes: number }[];
  reply_first: Review[];
  examples: Review[];
};

// ---- Pinboard ----------------------------------------------------------------------------------

export type Pin = Review & { note: string; pinned_at: string };

export const pinsApi = {
  list: (runId: string) => request<Pin[]>(`/runs/${runId}/pins`),
  pin: (runId: string, reviewId: string, note = "") =>
    request<Pin[]>(`/runs/${runId}/pins/${encodeURIComponent(reviewId)}`, { method: "PUT", body: JSON.stringify({ note }) }),
  unpin: (runId: string, reviewId: string) =>
    request<void>(`/runs/${runId}/pins/${encodeURIComponent(reviewId)}`, { method: "DELETE" }),
};

// ---- Saved API keys (encrypted on this computer; never returned) -------------------------------

export const keysApi = {
  list: () => request<{ protection: "keychain" | "file" | "provided"; keys: SavedKey[] }>("/keys"),
  save: (provider: string, apiKey: string, remember: boolean) =>
    request<SavedKey>(`/keys/${provider}`, { method: "PUT", body: JSON.stringify({ api_key: apiKey, remember }) }),
  remove: (provider: string) => request<void>(`/keys/${provider}`, { method: "DELETE" }),
};

// ---- AI-written decision artifacts --------------------------------------------------------------

export type Level = "high" | "medium" | "low";
export type DecisionStatus = "todo" | "planned" | "in_progress" | "done" | "dismissed";
export type CitedReviewFull = {
  review_id: string;
  rating: number;
  date: string | null;
  content: string;
  app_version: string;
  thumbs_up: number;
  themes: string[];
};

export type Decision = {
  id: string;
  title: string;
  lens: "design" | "product";
  action: string;
  theme: string;
  problem: string;
  evidence: string;
  review_ids: string[];
  who: string;
  root_causes: string[];
  how_might_we: string[];
  options: { idea: string; effort: Level }[];
  impact: Level;
  confidence: Level;
  effort: Level;
  score: number;
  priority: "now" | "next" | "later";
  metric: string;
  risk_of_inaction: string;
  status: DecisionStatus;
};

type Point = { heading: string; detail: string; review_ids: string[] };
type WithReviews = { reviews: Record<string, CitedReviewFull> };

export type ArtifactContent = {
  decisions: { decisions: Decision[] } & WithReviews;
  report: {
    title: string;
    summary: string;
    method: string;
    key_findings: Point[];
    user_needs: string[];
    opportunities: Point[];
    recommendations: { heading: string; detail: string; when: "now" | "next" | "later" }[];
    open_questions: string[];
  } & WithReviews;
  what_changed: {
    headline: string;
    compared: string | null;
    changes: { kind: "new" | "worse" | "better" | "steady"; theme: string; detail: string; review_ids: string[] }[];
    next_step: string;
  } & WithReviews;
  personas: {
    personas: {
      name: string;
      who: string;
      goals: string[];
      frustrations: string[];
      behaviours: string[];
      how_common: string;
      design_implications: string[];
      review_ids: string[];
    }[];
  } & WithReviews;
};
export type ArtifactKind = keyof ArtifactContent;
export type Artifact<K extends ArtifactKind> = {
  kind: K;
  content: ArtifactContent[K];
  provider: string;
  model: string;
  created_at: string;
};

export const artifactsApi = {
  get: <K extends ArtifactKind>(runId: string, kind: K) =>
    request<{ artifact: Artifact<K> | null }>(`/runs/${runId}/artifacts/${kind}`),
  generate: <K extends ArtifactKind>(runId: string, kind: K, llm: LLMConfig) =>
    request<{ artifact: Artifact<K> }>(`/runs/${runId}/artifacts/${kind}`, post({ llm })),
  setStatus: (runId: string, id: string, status: DecisionStatus) =>
    request<{ artifact: Artifact<"decisions"> }>(`/runs/${runId}/artifacts/decisions/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  markdownUrl: (runId: string) => `/api/runs/${runId}/artifacts/report/markdown`,
};

// ---- Benchmarks ---------------------------------------------------------------------------------

export type RunSummary = {
  reviews: number;
  avg_rating: number | null;
  negative_share: number | null;
  positive_share: number | null;
  churn_share: number | null;
  ratings: Record<string, number>;
  feedback_types: Record<string, number>;
  emotions: Record<string, number>;
  journey: Record<string, { reviews: number; share: number; negative_share: number }>;
  top_problems: { theme: string; reach: number; negative_share: number }[];
  top_strengths: { theme: string; reach: number }[];
};

export type BenchmarkBrief = {
  id: string;
  name: string;
  apps: { run_id: string; title: string; icon_url: string | null; country: string | null }[];
  updated_at: string;
};

type BenchPoint = { point: string; review_ids: string[]; subject?: string; scope?: string; evidence?: string };
export type BenchmarkInsights = {
  headline: string;
  topics: { name: string; apps: { themes: string[]; mentions: number; share: number; negative_share: number | null }[] }[];
  leads: BenchPoint[];
  lags: BenchPoint[];
  opportunities: BenchPoint[];
  reviews: Record<string, CitedReviewFull & { app?: string }>;
};

export type BenchmarkDetail = {
  id: string;
  name: string;
  columns: { run: Run; summary: RunSummary }[];
  insights: BenchmarkInsights | null;
  provider: string | null;
  model: string | null;
  updated_at: string;
};

export const benchmarksApi = {
  list: () => request<BenchmarkBrief[]>("/benchmarks"),
  create: (runIds: string[], name?: string) => request<BenchmarkBrief>("/benchmarks", post({ run_ids: runIds, name: name || null })),
  get: (id: string) => request<BenchmarkDetail>(`/benchmarks/${id}`),
  insights: (id: string, llm: LLMConfig) => request<BenchmarkDetail>(`/benchmarks/${id}/insights`, post({ llm })),
  remove: (id: string) => request<void>(`/benchmarks/${id}`, { method: "DELETE" }),
};
