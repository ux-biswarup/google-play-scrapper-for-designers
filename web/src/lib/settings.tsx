import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, keysApi, type LLMConfig, type Provider } from "./api";

// ---- AI connection ------------------------------------------------------
// Only the choice of provider, model and server URL is kept in the browser. API keys are saved by the
// backend in an encrypted vault on this computer and never come back to the browser, so nothing secret
// can be stolen from browser storage.

export type AIConnection = {
  provider: string;
  model: string;
  baseUrl: string;
};

/** What older versions stored: the key itself, in browser storage. Migrated to the vault on load. */
type LegacyConnection = AIConnection & { apiKey?: string; remember?: boolean };

const CONNECTION_KEY = "ri.ai-connection";

function loadConnection(): LegacyConnection | null {
  for (const store of [localStorage, sessionStorage]) {
    try {
      const raw = store.getItem(CONNECTION_KEY);
      if (raw) return JSON.parse(raw) as LegacyConnection;
    } catch {
      // ignore corrupt values
    }
  }
  return null;
}

function storeConnection(connection: AIConnection | null) {
  localStorage.removeItem(CONNECTION_KEY);
  sessionStorage.removeItem(CONNECTION_KEY);
  if (connection) {
    const { provider, model, baseUrl } = connection; // never persist anything else
    localStorage.setItem(CONNECTION_KEY, JSON.stringify({ provider, model, baseUrl }));
  }
}

export function toLLMConfig(connection: AIConnection, apiKey?: string): LLMConfig {
  return {
    provider: connection.provider,
    model: connection.model || undefined,
    api_key: apiKey || undefined, // only while testing a key that hasn't been saved yet
    base_url: connection.baseUrl || undefined,
  };
}

type ConnectionState = {
  connection: AIConnection | null;
  provider: Provider | undefined;
  providers: Provider[];
  /** True when there is enough to start an analysis (key from the app or .env, and a model). */
  ready: boolean;
  modelLabel: string;
  save: (connection: AIConnection) => void;
  clear: () => void;
};

const ConnectionContext = createContext<ConnectionState | null>(null);

export function ConnectionProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [connection, setConnection] = useState<AIConnection | null>(() => {
    const stored = loadConnection();
    return stored ? { provider: stored.provider, model: stored.model ?? "", baseUrl: stored.baseUrl ?? "" } : null;
  });
  const { data: providers = [] } = useQuery({ queryKey: ["providers"], queryFn: api.providers, staleTime: 60_000 });

  // One-time migration: move a key that an older version kept in browser storage into the vault, then erase it.
  useEffect(() => {
    const legacy = loadConnection();
    if (!legacy?.apiKey) return;
    keysApi
      .save(legacy.provider, legacy.apiKey, legacy.remember ?? true)
      .catch(() => undefined)
      .finally(() => {
        storeConnection({ provider: legacy.provider, model: legacy.model ?? "", baseUrl: legacy.baseUrl ?? "" });
        queryClient.invalidateQueries({ queryKey: ["providers"] });
      });
  }, [queryClient]);

  // Without a saved choice, fall back to a provider whose key and model are set in .env.
  const effective = useMemo<AIConnection | null>(() => {
    if (connection) return connection;
    const fromEnv = providers.find((p) => p.has_env_key && p.default_model);
    return fromEnv
      ? { provider: fromEnv.id, model: "", baseUrl: "" }
      : null;
  }, [connection, providers]);

  const provider = providers.find((p) => p.id === effective?.provider);
  const model = effective?.model || provider?.default_model || "";
  const hasKey = !!provider?.saved_key || !!provider?.has_env_key || provider?.requires_key === false;
  const signedIn = provider?.id !== "chatgpt" || provider.connected === true;
  const ready =
    !!provider && !!model && hasKey && signedIn && (!provider.requires_base_url || !!effective?.baseUrl);

  const save = useCallback((next: AIConnection) => {
    storeConnection(next);
    setConnection(next);
  }, []);
  const clear = useCallback(() => {
    storeConnection(null);
    setConnection(null);
  }, []);

  const value = useMemo(
    () => ({ connection: effective, provider, providers, ready, modelLabel: model, save, clear }),
    [effective, provider, providers, ready, model, save, clear],
  );
  return <ConnectionContext.Provider value={value}>{children}</ConnectionContext.Provider>;
}

export function useConnection(): ConnectionState {
  const value = useContext(ConnectionContext);
  if (!value) throw new Error("useConnection must be used inside ConnectionProvider");
  return value;
}

// ---- Theme ----------------------------------------------------------------

type Theme = "light" | "dark";
const ThemeContext = createContext<{ theme: Theme; toggle: () => void }>({ theme: "light", toggle: () => {} });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.classList.contains("dark") ? "dark" : "light",
  );
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("ri.theme", theme);
  }, [theme]);
  const toggle = useCallback(() => setTheme((t) => (t === "dark" ? "light" : "dark")), []);
  return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>;
}

export const useTheme = () => useContext(ThemeContext);
