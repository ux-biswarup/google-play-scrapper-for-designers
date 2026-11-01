import { useCallback, useEffect, useId, useState } from "react";
import { useNavigate } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Eye, EyeOff, KeyRound, ShieldCheck } from "lucide-react";
import { api, keysApi, type Provider } from "../lib/api";
import { toLLMConfig, useConnection, type AIConnection } from "../lib/settings";
import { Button, Field, Input, Notice, Select, cx } from "../components/ui";
import { QuickConnect } from "../components/QuickConnect";

const PROVIDER_NOTES: Record<string, string> = {
  anthropic: "Claude models. Uses an Anthropic API key.",
  openai: "GPT models. Uses an OpenAI API key.",
  gemini: "Gemini models. Uses a Google AI Studio key.",
  openrouter: "One key for Claude, GPT, Gemini, Llama and more.",
  groq: "Very fast open models. Uses a Groq key.",
  mistral: "Mistral models. Uses a Mistral key.",
  ollama: "Runs on this computer. Free, no key needed.",
  custom: "Any server with an OpenAI-compatible API.",
};

function ProviderOption({ provider, checked, onSelect }: { provider: Provider; checked: boolean; onSelect: () => void }) {
  return (
    <label
      className={cx(
        "flex cursor-pointer items-start gap-3 rounded-md border px-3 py-2.5 transition-colors",
        checked ? "border-ink bg-soft" : "border-line hover:bg-soft/60",
      )}
    >
      <input type="radio" name="provider" checked={checked} onChange={onSelect} className="mt-1 accent-current" />
      <span className="flex flex-col">
        <span className="font-medium">{provider.name}</span>
        <span className="text-sm text-muted">{PROVIDER_NOTES[provider.id]}</span>
      </span>
    </label>
  );
}

export function SettingsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { connection, providers, save } = useConnection();
  const [draft, setDraft] = useState<AIConnection>(connection ?? { provider: "openai", model: "", baseUrl: "" });
  const [showKey, setShowKey] = useState(false);
  const [saved, setSaved] = useState(false);
  // A typed key is held only in this component until it's saved to the encrypted vault.
  const [keyInput, setKeyInput] = useState("");
  const [remember, setRemember] = useState(true);
  const [replacing, setReplacing] = useState(false);
  const vault = useQuery({ queryKey: ["vault"], queryFn: keysApi.list, staleTime: 60_000 });
  const ids = { key: useId(), model: useId(), url: useId() };
  const provider = providers.find((p) => p.id === draft.provider);
  const update = (patch: Partial<AIConnection>) => {
    setSaved(false);
    setDraft((d) => ({ ...d, ...patch }));
  };

  const models = useMutation({ mutationFn: () => api.models(toLLMConfig(draft, keyInput)) });
  const test = useMutation({ mutationFn: () => api.testConnection(toLLMConfig(draft, keyInput)) });
  const savedKey = provider?.saved_key;
  const showKeyInput = !savedKey || replacing;

  const refreshKeys = () => {
    queryClient.invalidateQueries({ queryKey: ["providers"] });
    queryClient.invalidateQueries({ queryKey: ["vault"] });
  };
  const saveAll = useMutation({
    mutationFn: async () => {
      if (keyInput.trim()) await keysApi.save(draft.provider, keyInput.trim(), remember);
    },
    onSuccess: () => {
      setKeyInput("");
      setReplacing(false);
      refreshKeys();
      save(draft);
      setSaved(true);
    },
  });
  const removeKey = useMutation({ mutationFn: () => keysApi.remove(draft.provider), onSuccess: refreshKeys });

  // Preselect the model configured in .env for this provider.
  useEffect(() => {
    if (!draft.model && provider?.default_model) update({ model: provider.default_model });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider?.id]);

  const chooseProvider = (id: string) => {
    models.reset();
    test.reset();
    setKeyInput("");
    setReplacing(false);
    update({ provider: id, model: providers.find((p) => p.id === id)?.default_model ?? "", baseUrl: "" });
  };

  const keyOptional = provider?.has_env_key || provider?.requires_key === false;

  const chooseChatGPT = (model: string) => {
    const next: AIConnection = { provider: "chatgpt", model, baseUrl: "" };
    save(next);
    setDraft(next);
    queryClient.invalidateQueries({ queryKey: ["providers"] });
  };
  // OpenRouter's key was saved to the vault by the backend; just switch the connection to it.
  const openRouterConnected = useCallback(() => {
    const next: AIConnection = { provider: "openrouter", model: "", baseUrl: "" };
    save(next);
    setDraft(next);
    setSaved(false);
    queryClient.invalidateQueries({ queryKey: ["providers"] });
    queryClient.invalidateQueries({ queryKey: ["vault"] });
  }, [save, queryClient]);

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Connect an AI model</h1>
      <p className="mt-2 max-w-prose text-muted">
        Choose who reads and tags your reviews. Keys are saved encrypted on this computer, never in your browser, and are
        never shown again after you save them.
      </p>

      <div className="mt-8">
        <QuickConnect remember={remember} onUseChatGPT={chooseChatGPT} onOpenRouterConnected={openRouterConnected} />
      </div>

      <form
        className="mt-10 flex flex-col gap-8 border-t border-line pt-8"
        onSubmit={(e) => {
          e.preventDefault();
          saveAll.mutate();
        }}
      >
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm font-medium">Or use an API key</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {providers.filter((p) => p.id !== "chatgpt").map((p) => (
              <ProviderOption key={p.id} provider={p} checked={p.id === draft.provider} onSelect={() => chooseProvider(p.id)} />
            ))}
          </div>
        </fieldset>

        {provider?.id === "chatgpt" && (
          <p className="text-sm text-muted">
            You're using your ChatGPT plan ({draft.model}). Pick a provider above to switch to an API key.
          </p>
        )}
        {provider && provider.id !== "chatgpt" && (
          <div className="flex flex-col gap-5">
            {provider.requires_key !== false && provider.id !== "ollama" && (
              <Field
                label={keyOptional ? "API key (optional)" : "API key"}
                htmlFor={ids.key}
                hint={
                  provider.has_env_key
                    ? `Leave empty to use ${provider.env_var} from your .env file.`
                    : provider.key_url && (
                        <a href={provider.key_url} target="_blank" rel="noreferrer" className="underline underline-offset-2">
                          Get a {provider.name} key
                        </a>
                      )
                }
              >
                {showKeyInput ? (
                  <div className="flex flex-col gap-3">
                    <div className="relative">
                      <Input
                        id={ids.key}
                        type={showKey ? "text" : "password"}
                        autoComplete="off"
                        spellCheck={false}
                        value={keyInput}
                        onChange={(e) => {
                          setSaved(false);
                          setKeyInput(e.target.value);
                        }}
                        placeholder={provider.has_env_key ? "Using the key from .env" : "Paste your key"}
                        className="pr-10"
                      />
                      <button
                        type="button"
                        onClick={() => setShowKey((v) => !v)}
                        aria-label={showKey ? "Hide key" : "Show key"}
                        className="absolute inset-y-0 right-0 px-3 text-muted hover:text-ink"
                      >
                        {showKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                      </button>
                    </div>
                    <label className="flex items-start gap-3 text-sm">
                      <input
                        type="checkbox"
                        checked={remember}
                        onChange={(e) => setRemember(e.target.checked)}
                        className="mt-0.5 size-4 accent-current"
                      />
                      <span>
                        <span className="font-medium">Keep this key after the app restarts</span>
                        <span className="block text-muted">
                          {remember
                            ? "Saved encrypted on this computer. Refreshing or closing the tab won't lose it."
                            : "Kept only in the app's memory until it stops. Nothing is written to disk."}
                        </span>
                      </span>
                    </label>
                    {replacing && (
                      <div>
                        <Button type="button" variant="ghost" size="sm" onClick={() => setReplacing(false)}>
                          Keep the saved key
                        </Button>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="flex flex-wrap items-center gap-3 rounded-md border border-line bg-panel px-3 py-2.5">
                    <KeyRound className="size-4 text-muted" aria-hidden />
                    <div className="min-w-0 flex-1 text-sm">
                      <p>
                        Saved key <code className="rounded bg-soft px-1.5 py-0.5 text-xs">{savedKey!.hint}</code>
                        {savedKey!.storage === "session" && <span className="text-muted"> for this session only</span>}
                      </p>
                      <p className="flex items-center gap-1 text-xs text-muted">
                        <ShieldCheck className="size-3.5 text-pos" aria-hidden />
                        {vault.data?.protection === "keychain"
                          ? "Encrypted on this computer; the encryption key is in your system keychain."
                          : "Encrypted on this computer; the encryption key file is readable only by you."}
                      </p>
                    </div>
                    <Button type="button" size="sm" onClick={() => setReplacing(true)}>
                      Replace
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="danger"
                      busy={removeKey.isPending}
                      onClick={() => window.confirm(`Remove the saved ${provider.name} key from this computer?`) && removeKey.mutate()}
                    >
                      Remove
                    </Button>
                  </div>
                )}
              </Field>
            )}

            {(provider.requires_base_url || provider.id === "ollama") && (
              <Field label="Server URL" htmlFor={ids.url} hint={provider.base_url ? `Default: ${provider.base_url}` : "For example http://localhost:8080/v1"}>
                <Input
                  id={ids.url}
                  value={draft.baseUrl}
                  onChange={(e) => update({ baseUrl: e.target.value })}
                  placeholder={provider.base_url ?? "https://"}
                />
              </Field>
            )}

            <Field
              label="Model"
              htmlFor={ids.model}
              hint="A smaller, cheaper model works well for tagging reviews. Load the list to see what your key can use."
            >
              <div className="flex gap-2">
                <Input
                  id={ids.model}
                  value={draft.model}
                  onChange={(e) => update({ model: e.target.value })}
                  placeholder="Model ID"
                  spellCheck={false}
                  autoComplete="off"
                />
                <Button type="button" onClick={() => models.mutate()} busy={models.isPending} className="shrink-0">
                  Load models
                </Button>
              </div>
            </Field>
            {models.isSuccess && (
              <Select aria-label="Available models" value={draft.model} onChange={(e) => update({ model: e.target.value })}>
                <option value="">Pick one of {models.data.models.length} available models</option>
                {models.data.models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </Select>
            )}
            {models.isError && <Notice tone="error" title="Couldn't load models">{models.error.message}</Notice>}

            {test.isSuccess && (
              <Notice title={`Connected. ${draft.model} answered in ${(test.data.latency_ms / 1000).toFixed(1)} s.`} />
            )}
            {test.isError && <Notice tone="error" title="Connection failed">{test.error.message}</Notice>}
            {saveAll.isError && <Notice tone="error" title="Couldn't save the key">{saveAll.error.message}</Notice>}

            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" variant="primary" disabled={!draft.model} busy={saveAll.isPending}>
                Save connection
              </Button>
              <Button type="button" onClick={() => test.mutate()} busy={test.isPending} disabled={!draft.model}>
                Test connection
              </Button>
              {saved && (
                <>
                  <span className="inline-flex items-center gap-1.5 text-sm text-pos">
                    <CheckCircle2 className="size-4" aria-hidden /> Saved
                  </span>
                  <Button type="button" variant="ghost" onClick={() => navigate("/new")}>
                    Analyze an app
                  </Button>
                </>
              )}
            </div>
          </div>
        )}
      </form>
    </div>
  );
}
