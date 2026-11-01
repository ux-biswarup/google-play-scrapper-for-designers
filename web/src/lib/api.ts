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
};

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
  output_language: string;
  provider: string;
  model: string;
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

  estimate: (count: number) => request<Estimate>("/runs/estimate", post({ count })),
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

export const chatApi = {
  get: (runId: string) => request<{ turns: ChatTurn[]; suggestions: string[] }>(`/runs/${runId}/chat`),
  clear: (runId: string) => request<void>(`/runs/${runId}/chat`, { method: "DELETE" }),

  /** Send a message and yield the streamed reply events. */
  async *send(runId: string, message: string, llm: LLMConfig, signal: AbortSignal): AsyncGenerator<ChatEvent> {
    const res = await fetch(`/api/runs/${runId}/chat`, {
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
