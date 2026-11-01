import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type LLMConfig, type Provider } from "./api";

// ---- AI connection ------------------------------------------------------
// The key is sent only to this app's own backend. With "remember" off it lives in
// sessionStorage and disappears when the tab closes.

export type AIConnection = {
  provider: string;
  model: string;
  apiKey: string;
  baseUrl: string;
  remember: boolean;
};

const CONNECTION_KEY = "ri.ai-connection";

function loadConnection(): AIConnection | null {
  for (const store of [localStorage, sessionStorage]) {
    try {
      const raw = store.getItem(CONNECTION_KEY);
      if (raw) return JSON.parse(raw) as AIConnection;
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
    (connection.remember ? localStorage : sessionStorage).setItem(CONNECTION_KEY, JSON.stringify(connection));
  }
}

export function toLLMConfig(connection: AIConnection): LLMConfig {
  return {
    provider: connection.provider,
    model: connection.model || undefined,
    api_key: connection.apiKey || undefined,
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
  const [connection, setConnection] = useState<AIConnection | null>(loadConnection);
  const { data: providers = [] } = useQuery({ queryKey: ["providers"], queryFn: api.providers, staleTime: 60_000 });

  // Without a saved choice, fall back to a provider whose key and model are set in .env.
  const effective = useMemo<AIConnection | null>(() => {
    if (connection) return connection;
    const fromEnv = providers.find((p) => p.has_env_key && p.default_model);
    return fromEnv
      ? { provider: fromEnv.id, model: "", apiKey: "", baseUrl: "", remember: false }
      : null;
  }, [connection, providers]);

  const provider = providers.find((p) => p.id === effective?.provider);
  const model = effective?.model || provider?.default_model || "";
  const hasKey = !!effective?.apiKey || !!provider?.has_env_key || provider?.requires_key === false;
  const ready = !!provider && !!model && hasKey && (!provider.requires_base_url || !!effective?.baseUrl);

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
