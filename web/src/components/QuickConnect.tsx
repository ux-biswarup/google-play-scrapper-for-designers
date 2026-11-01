import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { api, authApi } from "../lib/api";
import { useConnection } from "../lib/settings";
import { Badge, Button, Notice, Select } from "./ui";

const MANAGE_USAGE_URL = "https://chatgpt.com/#settings";
const PLAN_HELP_URL = "https://help.openai.com/";
const OPENROUTER_PENDING = "ri.openrouter-pending";

const b64url = (bytes: Uint8Array) =>
  btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

/** OpenRouter's OAuth PKCE login: the browser keeps the verifier, the backend swaps the code for a key. */
async function startOpenRouter(remember: boolean) {
  const verifier = b64url(crypto.getRandomValues(new Uint8Array(48)));
  const challenge = b64url(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier))));
  sessionStorage.setItem(OPENROUTER_PENDING, JSON.stringify({ verifier, remember }));
  const query = new URLSearchParams({
    callback_url: `${location.origin}/settings?openrouter=1`,
    code_challenge: challenge,
    code_challenge_method: "S256",
  });
  location.href = `https://openrouter.ai/auth?${query}`;
}

function ChatGPTCard({ onUse }: { onUse: (model: string) => void }) {
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const { connection } = useConnection();
  const status = useQuery({ queryKey: ["chatgpt-status"], queryFn: authApi.chatgptStatus });
  const [model, setModel] = useState(connection?.provider === "chatgpt" ? connection.model : "");
  const [welcome, setWelcome] = useState(
    params.get("chatgpt") === "connected" && !localStorage.getItem("ri.chatgpt-welcomed"),
  );
  const signedIn = status.data?.signed_in;
  const models = useQuery({
    queryKey: ["chatgpt-models"],
    queryFn: () => api.models({ provider: "chatgpt" }),
    enabled: !!status.data?.plan_usage,
    retry: false,
  });
  const start = useMutation({
    mutationFn: () => authApi.chatgptStart(location.origin),
    onSuccess: ({ url }) => {
      location.href = url;
    },
  });
  const signOut = useMutation({
    mutationFn: authApi.chatgptSignOut,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["chatgpt-status"] });
      queryClient.invalidateQueries({ queryKey: ["providers"] });
    },
  });

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-line bg-panel p-5">
      <div className="flex items-center gap-2">
        <h3 className="font-semibold">Use your ChatGPT plan</h3>
        <Badge>Preview</Badge>
      </div>
      {welcome && (
        <Notice title="You're using your ChatGPT plan">
          Analyses and the assistant now run on your ChatGPT plan, separate from any API billing. You can manage usage in
          ChatGPT settings.{" "}
          <button
            className="font-medium text-ink underline underline-offset-2"
            onClick={() => {
              localStorage.setItem("ri.chatgpt-welcomed", "1");
              setWelcome(false);
            }}
          >
            Got it
          </button>
        </Notice>
      )}
      {params.get("chatgpt_error") && <Notice tone="error" title="Sign-in didn't complete">{params.get("chatgpt_error")}</Notice>}

      {!signedIn ? (
        <>
          <p className="text-sm text-muted">
            For ChatGPT Plus and Pro. Analyses and the assistant use your ChatGPT plan instead of an API key; you can
            manage usage in ChatGPT settings.{" "}
            <a href={PLAN_HELP_URL} target="_blank" rel="noreferrer" className="underline underline-offset-2">
              Learn more
            </a>
          </p>
          <div>
            <Button variant="brand" onClick={() => start.mutate()} busy={start.isPending}>
              Continue with ChatGPT
            </Button>
          </div>
          {start.isError && <Notice tone="error" title="Couldn't start sign-in">{start.error.message}</Notice>}
        </>
      ) : !status.data?.plan_usage ? (
        <>
          <Notice tone="error" title="Plan usage isn't available for this account">
            Signed in as {status.data?.email}, but this account didn't grant ChatGPT plan usage. It needs an eligible Plus
            or Pro plan. Use an API key below instead.
          </Notice>
          <div>
            <Button size="sm" onClick={() => signOut.mutate()} busy={signOut.isPending}>
              Sign out
            </Button>
          </div>
        </>
      ) : (
        <>
          <p className="flex flex-wrap items-center gap-x-2 text-sm">
            <CheckCircle2 className="size-4 text-pos" aria-hidden /> Signed in as {status.data.email}.
            <a href={MANAGE_USAGE_URL} target="_blank" rel="noreferrer" className="text-muted underline underline-offset-2">
              Manage usage
            </a>
          </p>
          {models.isError && <Notice tone="error" title="Couldn't load your models">{models.error.message}</Notice>}
          <div className="flex flex-wrap items-center gap-2">
            <Select aria-label="ChatGPT model" value={model} onChange={(e) => setModel(e.target.value)} className="w-64">
              <option value="">{models.isLoading ? "Loading models…" : "Choose a model"}</option>
              {models.data?.models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </Select>
            <Button variant="primary" disabled={!model} onClick={() => onUse(model)}>
              {connection?.provider === "chatgpt" && connection.model === model ? "In use" : "Use ChatGPT plan"}
            </Button>
            <Button variant="ghost" size="sm" onClick={() => signOut.mutate()} busy={signOut.isPending}>
              Sign out
            </Button>
          </div>
          {signOut.data && !signOut.data.revoked && (
            <p className="text-sm text-muted">
              Signed out here. OpenAI didn't confirm the sign-out; you can also disconnect the app in ChatGPT settings.
            </p>
          )}
        </>
      )}
    </section>
  );
}

function OpenRouterCard({ remember, onConnected }: { remember: boolean; onConnected: (key: string, remember: boolean) => void }) {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const handled = useRef(false);
  const exchange = useMutation({
    mutationFn: ({ code, verifier }: { code: string; verifier: string }) => authApi.openrouterExchange(code, verifier),
  });

  // Back from OpenRouter's login page with ?openrouter=1&code=...
  useEffect(() => {
    const code = params.get("code");
    if (handled.current || params.get("openrouter") !== "1" || !code) return;
    handled.current = true;
    const pending = JSON.parse(sessionStorage.getItem(OPENROUTER_PENDING) ?? "null") as
      | { verifier: string; remember: boolean }
      | null;
    sessionStorage.removeItem(OPENROUTER_PENDING);
    navigate("/settings", { replace: true }); // drop the one-time code from the address bar
    if (!pending) return;
    exchange.mutate(
      { code, verifier: pending.verifier },
      { onSuccess: ({ key }) => onConnected(key, pending.remember) },
    );
  }, [params, navigate, exchange, onConnected]);

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-line bg-panel p-5">
      <h3 className="font-semibold">Connect OpenRouter</h3>
      <p className="text-sm text-muted">
        One sign-in for Claude, GPT, Gemini, Llama and more, paid from your OpenRouter credits. No key to copy.
      </p>
      {exchange.isSuccess && (
        <p className="flex items-center gap-2 text-sm">
          <CheckCircle2 className="size-4 text-pos" aria-hidden /> Connected. Choose a model below and save.
        </p>
      )}
      {exchange.isError && <Notice tone="error" title="Couldn't connect OpenRouter">{exchange.error.message}</Notice>}
      <div>
        <Button onClick={() => startOpenRouter(remember)} busy={exchange.isPending}>
          {exchange.isSuccess ? "Reconnect OpenRouter" : "Connect OpenRouter"}
        </Button>
      </div>
    </section>
  );
}

export function QuickConnect({
  remember,
  onUseChatGPT,
  onOpenRouterKey,
}: {
  remember: boolean;
  onUseChatGPT: (model: string) => void;
  onOpenRouterKey: (key: string, remember: boolean) => void;
}) {
  return (
    <section aria-labelledby="quick-connect" className="flex flex-col gap-3">
      <h2 id="quick-connect" className="text-sm font-medium">
        Sign in with an account you already have
      </h2>
      <div className="grid gap-3 md:grid-cols-2">
        <ChatGPTCard onUse={onUseChatGPT} />
        <OpenRouterCard remember={remember} onConnected={onOpenRouterKey} />
      </div>
      <p className="text-sm text-muted">
        Already pay for Claude or ChatGPT?{" "}
        <Link to="/connect" className="font-medium text-ink underline underline-offset-2">
          Ask about your analyses inside Claude, ChatGPT, Cursor and more
        </Link>
        .
      </p>
    </section>
  );
}
