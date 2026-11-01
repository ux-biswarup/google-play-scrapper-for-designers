import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy } from "lucide-react";
import { connectApi, type McpInfo } from "../lib/api";
import { Notice, Segmented, Spinner } from "../components/ui";

type AppId = "claude-desktop" | "claude-code" | "cursor" | "vscode" | "codex" | "web";

type Setup = { where: string; steps: string[]; snippet: string; language: string; needsAppRunning: boolean };

function setups(info: McpInfo): Record<AppId, Setup> {
  const stdio = {
    command: info.python,
    args: ["-m", info.module],
    env: { PYTHONPATH: info.project_dir },
  };
  return {
    "claude-desktop": {
      where: "Claude Desktop",
      steps: [
        "Open Claude Desktop, then Settings, Developer, Edit config.",
        "Paste this into claude_desktop_config.json (merge it if the file already has servers).",
        "Restart Claude Desktop. Ask: “What are the biggest problems in my latest analysis?”",
      ],
      snippet: JSON.stringify({ mcpServers: { [info.server_name]: stdio } }, null, 2),
      language: "json",
      needsAppRunning: false,
    },
    "claude-code": {
      where: "Claude Code",
      steps: ["Run this once in a terminal.", "Then ask Claude Code about your analyses in any project."],
      snippet: `claude mcp add ${info.server_name} --scope user --env PYTHONPATH="${info.project_dir}" -- "${info.python}" -m ${info.module}`,
      language: "shell",
      needsAppRunning: false,
    },
    cursor: {
      where: "Cursor",
      steps: ["Open ~/.cursor/mcp.json (create it if needed) and paste this.", "Keep Review Insights running while you use it."],
      snippet: JSON.stringify({ mcpServers: { [info.server_name]: { url: info.http_url } } }, null, 2),
      language: "json",
      needsAppRunning: true,
    },
    vscode: {
      where: "VS Code (Copilot agent mode)",
      steps: ["Add this to .vscode/mcp.json in your workspace, or to your user MCP settings.", "Keep Review Insights running while you use it."],
      snippet: JSON.stringify({ servers: { [info.server_name]: { type: "http", url: info.http_url } } }, null, 2),
      language: "json",
      needsAppRunning: true,
    },
    codex: {
      where: "Codex CLI",
      steps: ["Add this to ~/.codex/config.toml.", "Start a new Codex session and ask about your analyses."],
      snippet: [
        `[mcp_servers.${info.server_name}]`,
        `command = "${info.python}"`,
        `args = ["-m", "${info.module}"]`,
        `env = { PYTHONPATH = "${info.project_dir}" }`,
      ].join("\n"),
      language: "toml",
      needsAppRunning: false,
    },
    web: {
      where: "ChatGPT or claude.ai in the browser",
      steps: [
        "Web apps can only reach servers on the public internet, not this computer. Expose the app with a tunnel such as Cloudflare Tunnel or ngrok, then add the tunnel's HTTPS address plus /mcp/ as a custom connector (ChatGPT: Settings, Apps & Connectors, developer mode; claude.ai: Settings, Connectors).",
        "Start the app with MCP_ALLOWED_HOSTS set to the tunnel's host name, or requests will be refused.",
        "Anyone with the tunnel address can read your analyses, so stop the tunnel when you're done.",
      ],
      snippet: `MCP_ALLOWED_HOSTS=your-tunnel.example.com uvicorn backend.main:app --port 8000\n# connector URL: https://your-tunnel.example.com/mcp/`,
      language: "shell",
      needsAppRunning: true,
    },
  };
}

function CopyBlock({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="relative">
      <pre className="overflow-x-auto rounded-md border border-line bg-paper p-4 pr-24 text-sm leading-relaxed">
        <code>{text}</code>
      </pre>
      <button
        onClick={async () => {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        }}
        className="absolute right-2 top-2 inline-flex h-8 items-center gap-1.5 rounded-md border border-line bg-panel px-2.5 text-sm hover:bg-soft"
        aria-label={`Copy ${label}`}
      >
        {copied ? <Check className="size-4 text-pos" aria-hidden /> : <Copy className="size-4" aria-hidden />}
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

export function ConnectPage() {
  const info = useQuery({ queryKey: ["mcp-info"], queryFn: connectApi.mcp, staleTime: Infinity });
  const [app, setApp] = useState<AppId>("claude-desktop");

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Use your analyses in other AI apps</h1>
      <p className="mt-2 max-w-prose text-muted">
        Connect Claude, ChatGPT, Cursor or another app you already pay for. It can then read your analyses and answer
        questions with numbers and real quotes, using your own subscription. It can only read; it can't start analyses
        or change anything.
      </p>

      {info.isLoading && <div className="mt-8"><Spinner /></div>}
      {info.error && <div className="mt-8"><Notice tone="error" title="Couldn't load connection details">{info.error.message}</Notice></div>}
      {info.data && (
        <div className="mt-8 flex flex-col gap-6">
          <div className="overflow-x-auto">
            <Segmented
              label="App"
              value={app}
              onChange={setApp}
              options={[
                { value: "claude-desktop", label: "Claude Desktop" },
                { value: "claude-code", label: "Claude Code" },
                { value: "cursor", label: "Cursor" },
                { value: "vscode", label: "VS Code" },
                { value: "codex", label: "Codex" },
                { value: "web", label: "ChatGPT / claude.ai" },
              ]}
            />
          </div>
          {(() => {
            const setup = setups(info.data)[app];
            return (
              <section className="flex flex-col gap-4" aria-label={setup.where}>
                <ol className="flex list-decimal flex-col gap-2 pl-5">
                  {setup.steps.map((step) => (
                    <li key={step} className="max-w-prose">{step}</li>
                  ))}
                </ol>
                <CopyBlock text={setup.snippet} label={`${setup.where} setup`} />
                <p className="text-sm text-muted">
                  {setup.needsAppRunning
                    ? `Connects to ${info.data.http_url}, so Review Insights must be running.`
                    : "The app starts its own connection, so Review Insights doesn't need to be open."}
                </p>
              </section>
            );
          })()}

          <section className="border-t border-line pt-6">
            <h2 className="font-semibold">What the connected app can do</h2>
            <ul className="mt-3 flex flex-col gap-2 text-sm">
              {info.data.tools.map((t) => (
                <li key={t.name}>
                  <code className="rounded bg-soft px-1.5 py-0.5 text-xs">{t.name}</code>{" "}
                  <span className="text-muted">{t.description}</span>
                </li>
              ))}
            </ul>
          </section>
        </div>
      )}
    </div>
  );
}
