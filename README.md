# Review Insights

![Cover Image](google-play-store-scraper-for-designers.png)

Turn Google Play reviews into design and product decisions. Review Insights downloads an app's reviews, has an AI model of your choice tag every review (feedback type, themes, journey stage, emotion, severity, user type, churn risk), and shows designers and PMs what to fix, build, redesign or protect, always with the real quotes behind each point.

**Copyright © 2026 [Biswarup Mondal](https://www.biswarupmondal.com)**

## What you get for each analysis

**Decide**
- **Decisions:** ranked design and product decisions (fix, redesign, build, reconsider, protect) in Now / Next / Later, each with evidence, likely causes, How Might We questions, options, a metric to watch and a status you can track
- **Research report:** a shareable UX research report with quotes; download as Markdown or save as PDF

**Understand**
- **Overview:** rating, sentiment, feedback-type, journey and emotion breakdowns, and the biggest problems
- **Problems & priorities:** themes ranked by impact (reach × negativity × momentum) and a priority matrix
- **Bugs, requests, complaints:** what to fix, what to build, what to redesign, what to reconsider
- **Journey map:** an emotional curve across onboarding, login, core use, payments and support, with the biggest pain point
- **Emotions:** what each feeling implies, which themes trigger it, and how it changes over time
- **Segments:** new vs long-time vs paying users, app versions, upvoted reviews, detailed reviews, developer replies
- **Risks:** people who say they're leaving and why, competitors they name, money problems
- **Personas:** proto-personas drafted from reviews, clearly marked as hypotheses

**Track and explore**
- **Trends & what changed:** a written summary of what got better or worse in the latest release (labels computed from the numbers), sentiment over time, one-star spikes, trending themes, before/after a release
- **Any period:** analyze any time, the last 7/30/90 days or a custom date range; the app counts the reviews in that period first so you choose how many to analyze
- **Reviews:** filter by rating, theme, type, journey stage, emotion, version or text
- **Research assistant:** ask questions; answers look up the analysis and cite the exact reviews
- **Chart images** (PNG/SVG) for slides and reports

Churn and competitor tags are only kept when the review says so in its own words, so they aren't invented.

## Bring your own AI

Pick a provider and model in the app's settings:

- **API key:** Anthropic (Claude), OpenAI, Google Gemini, OpenRouter, Groq, Mistral, or any OpenAI-compatible server
- **Local and free:** Ollama
- **Sign in instead of pasting a key:** "Continue with ChatGPT" (uses a ChatGPT Plus/Pro plan; preview) or "Connect OpenRouter"
- **Use your analyses inside other AI apps:** the built-in MCP server works with Claude Desktop, Claude Code, Cursor, VS Code, Codex and ChatGPT. The app's "Use in Claude, ChatGPT…" page has copy-paste setup.

Keys entered in the app are kept in memory on your computer and never stored in the database. Optionally, put fallback keys in `.env` (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`) and a preselected model per provider (`OPENAI_MODEL`, …).

## Run it

Requires Python 3.11+ and Node.js 24 (`nvm use` reads `.nvmrc`).

```bash
git clone https://github.com/ux-biswarup/google-play-scrapper-for-designers.git
cd google-play-scrapper-for-designers

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cd web && nvm use && npm install && npm run build && cd ..
uvicorn backend.main:app --port 8000
```

Open http://127.0.0.1:8000, connect an AI model in Settings, and analyze an app by name or Play Store link.

Results are stored locally in `data/app.db` (git-ignored). Analyses made with the earlier Streamlit version can be imported from `reports/` with `python -m backend.cli import-legacy`.

## Develop

- Frontend with hot reload: `cd web && npm run dev`, then open http://localhost:5173 (it proxies `/api` to the backend)
- API docs: http://127.0.0.1:8000/docs
- MCP server over stdio: `python -m backend.mcp_server`; over HTTP: `http://127.0.0.1:8000/mcp/`
- Tests: `pytest` (offline, no API keys needed). Lint: `ruff check backend tests` and `ruff format backend tests`
- CI runs lint, tests on Python 3.11–3.14, the frontend build and a smoke test of the running server

| Folder | What's in it |
| --- | --- |
| `backend/` | FastAPI app, AI providers, analysis pipeline, metrics layer, decision views, assistant tools, MCP server |
| `web/` | React + TypeScript + Vite + Tailwind interface with Plotly charts |
| `tests/unit/` | Offline tests with a fake Play Store and a fake AI model |

## Roadmap

- **Benchmark:** compare analyses of competitors, markets or periods
- **Accessibility and developer replies:** dedicated views
- **iOS reviews**

## Security

- **API keys never live in the browser.** Keys you paste are saved by the backend, encrypted (AES + HMAC) in `data/secrets.enc`; the encryption key is kept in your operating system's keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service), or in an owner-only file where no keychain exists. The app only ever shows a masked hint. Choose "this session only" to keep a key in memory until the app stops.
- ChatGPT sign-in tokens are encrypted the same way.
- The server answers only on local host names and refuses changes requested by other websites, so a page open in your browser can't use your saved keys. App pages use a strict Content-Security-Policy.
- The MCP endpoint only accepts local requests unless you set `MCP_ALLOWED_HOSTS`.
- `.env` and other credential files are git-ignored. Optionally install the pre-commit hook that blocks committing them:
  `cp .github/pre-commit-hook.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit`

## License

MIT. See [LICENSE](LICENSE).
