import { useEffect, useId, useState } from "react";
import { useNavigate } from "react-router";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Eye, EyeOff } from "lucide-react";
import { api, type Provider } from "../lib/api";
import { toLLMConfig, useConnection, type AIConnection } from "../lib/settings";
import { Button, Field, Input, Notice, Select, cx } from "../components/ui";

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
  const { connection, providers, save } = useConnection();
  const [draft, setDraft] = useState<AIConnection>(
    connection ?? { provider: "openai", model: "", apiKey: "", baseUrl: "", remember: false },
  );
  const [showKey, setShowKey] = useState(false);
  const [saved, setSaved] = useState(false);
  const ids = { key: useId(), model: useId(), url: useId(), models: useId() };
  const provider = providers.find((p) => p.id === draft.provider);
  const update = (patch: Partial<AIConnection>) => {
    setSaved(false);
    setDraft((d) => ({ ...d, ...patch }));
  };

  const models = useMutation({ mutationFn: () => api.models(toLLMConfig(draft)) });
  const test = useMutation({ mutationFn: () => api.testConnection(toLLMConfig(draft)) });

  // Preselect the model configured in .env for this provider.
  useEffect(() => {
    if (!draft.model && provider?.default_model) update({ model: provider.default_model });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provider?.id]);

  const chooseProvider = (id: string) => {
    models.reset();
    test.reset();
    update({ provider: id, model: providers.find((p) => p.id === id)?.default_model ?? "", baseUrl: "" });
  };

  const keyOptional = provider?.has_env_key || provider?.requires_key === false;

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Connect an AI model</h1>
      <p className="mt-2 max-w-prose text-muted">
        Choose who reads and tags your reviews. Your key is sent only to this app's backend on your computer and is never
        saved in its database.
      </p>

      <form
        className="mt-8 flex flex-col gap-8"
        onSubmit={(e) => {
          e.preventDefault();
          save(draft);
          setSaved(true);
        }}
      >
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-sm font-medium">Provider</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {providers.map((p) => (
              <ProviderOption key={p.id} provider={p} checked={p.id === draft.provider} onSelect={() => chooseProvider(p.id)} />
            ))}
          </div>
        </fieldset>

        {provider && (
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
                <div className="relative">
                  <Input
                    id={ids.key}
                    type={showKey ? "text" : "password"}
                    autoComplete="off"
                    spellCheck={false}
                    value={draft.apiKey}
                    onChange={(e) => update({ apiKey: e.target.value })}
                    placeholder={provider.has_env_key ? "Using the key from .env" : "Paste your key"}
                    className="pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowKey((s) => !s)}
                    aria-label={showKey ? "Hide key" : "Show key"}
                    className="absolute inset-y-0 right-0 px-3 text-muted hover:text-ink"
                  >
                    {showKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
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
                  list={ids.models}
                  value={draft.model}
                  onChange={(e) => update({ model: e.target.value })}
                  placeholder="Model ID"
                  spellCheck={false}
                />
                <datalist id={ids.models}>
                  {models.data?.models.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                </datalist>
                <Button type="button" onClick={() => models.mutate()} busy={models.isPending} className="shrink-0">
                  Load models
                </Button>
              </div>
            </Field>
            {models.isSuccess && (
              <Select aria-label="Available models" value={draft.model} onChange={(e) => update({ model: e.target.value })}>
                <option value="">Choose from {models.data.models.length} models</option>
                {models.data.models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </Select>
            )}
            {models.isError && <Notice tone="error" title="Couldn't load models">{models.error.message}</Notice>}

            <label className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                checked={draft.remember}
                onChange={(e) => update({ remember: e.target.checked })}
                className="mt-0.5 size-4 accent-current"
              />
              <span>
                <span className="font-medium">Remember on this device</span>
                <span className="block text-muted">When off, the key is forgotten when you close this tab.</span>
              </span>
            </label>

            {test.isSuccess && (
              <Notice title={`Connected. ${draft.model} answered in ${(test.data.latency_ms / 1000).toFixed(1)} s.`} />
            )}
            {test.isError && <Notice tone="error" title="Connection failed">{test.error.message}</Notice>}

            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" variant="primary" disabled={!draft.model}>
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
