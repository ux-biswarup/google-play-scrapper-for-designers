<p align="center">
  <img src="web/public/logo.svg" width="88" height="88" alt="Review Insights logo">
</p>

<h1 align="center">Review Insights</h1>

<p align="center">
  <strong>Turn Google Play reviews into design and product decisions, with the real reviews behind every point.</strong>
</p>

<p align="center">
  <a href="https://github.com/ux-biswarup/google-play-scrapper-for-designers/actions/workflows/ci.yml"><img src="https://github.com/ux-biswarup/google-play-scrapper-for-designers/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
</p>

Review Insights is a free, open-source **Google Play review analyzer for product managers and UX designers**. Paste an
app's name or Play Store link. It reads thousands of reviews for you and gives you three things:
- ranked decisions: what to fix, redesign, build or protect;
- a journey map, competitor benchmarks and a research report;
- an AI research assistant that answers your questions and quotes the users who said it.

It runs on your computer and works with the AI you already have: Claude, ChatGPT, Gemini, OpenRouter, Groq,
Mistral or a local model.

![Analysis overview with the research assistant answering a question and citing reviews](docs/images/assistant.png)

**Copyright © 2026 [Biswarup Mondal](https://www.biswarupmondal.com)**

---

## Why it exists

App reviews are the largest free source of user feedback most teams have, and the least used. Reading thousands of
them takes days. Sentiment dashboards tell you 40% are negative, but not what to change on Monday.

Review Insights reads every review and works out how much each problem matters. It turns that into decisions you can
defend in a design critique or a roadmap meeting. Every number links back to the reviews it came from, and every claim
quotes the users' own words.

## What it does for you

**For product managers**
- **A prioritized decision list.** Each item is sorted into Now, Next or Later by impact × confidence ÷ effort, with
  evidence, options, a metric to watch and a status you can track.
- **What changed in the last release.** See what got better or worse and which version caused it. The labels come from
  the numbers, not from the AI.
- **Early warnings.** People who say they're leaving and why, competitors they name, payment problems and rising
  complaints.
- **Competitor benchmarks.** Put your app next to up to three others to see where you lead, where you lag and what to
  learn from them.
- **Stakeholder-ready output.** Download a research report as Markdown or PDF, export charts as images, or ask the
  assistant for a one-paragraph update.

**For product designers and UX researchers**
- **Where the experience breaks.** An emotional curve across onboarding, sign-in, core use, payments and support, with
  the most painful step marked.
- **Usability problems ranked by impact,** not by how loud they are, each with quotes for your next critique.
- **A faster start to research.** How Might We questions, likely root causes and draft proto-personas, clearly marked as
  hypotheses.
- **Accessibility barriers users report,** grouped by need (text size, contrast, screen readers, motion, touch, hearing,
  mobility), each with the WCAG check to run.
- **Pinned quotes.** Collect the reviews that make your case while you explore, add a note to each, and drop them into
  decks, tickets and the research report.

## The decision intelligence layer

Most AI review tools ask a model to "summarize the reviews", and you get confident text you can't check. Review
Insights splits the work into three layers so you can trust the result:

1. **Evidence.** The AI tags each review:
   - feedback type (bug, request, friction, complaint or praise);
   - themes, journey stage and emotion;
   - severity, user type, churn risk and accessibility.

   Risky tags are double-checked. "They're leaving" and competitor names are only kept when the review says so in its
   own words.
2. **Analysis, computed in code.** Counts, shares, trends and scores are calculated, never written by the model:
   - impact = reach × negativity × momentum;
   - priority = impact × confidence ÷ effort.

   Labels like better or worse, leads and lags come from the numbers.
3. **Decisions, written by AI and checked.** The model explains and recommends, citing review IDs. Any citation to a
   review that doesn't exist is removed, so every claim points to real feedback.

## Your research assistant: from question to decision

The assistant (**Ask AI**, top right of every analysis) is the fastest way to go from "what's going on?" to a decision
you can defend.

**It works from your data, not from memory.** To answer, the assistant looks things up in the analysis: the problem
board, the journey map, segments, trends, risks, and a search across the reviews. You can watch each lookup as it
happens ("Read the journey map", "Searched reviews 'login'"). Numbers come from those lookups, and every claim is cited.
Click a citation number to read the review it came from.

**It suggests the right first questions.** Each analysis gets up to five starter questions written from what it found,
each tagged with why it's there:

| Tag | Example for Pokémon GO |
| --- | --- |
| Top problem | Why are users unhappy about login issues? |
| Rising | What's behind the recent rise in account management complaints? |
| Churn risk | Why do 17 reviewers say they're leaving, and what would keep them? |
| Journey | Where do users get stuck with the core experience? |
| Release | Did version 0.435.1 make things better or worse? |

Other tags appear when the data supports them: Competitor, Request, Money, Strength and Accessibility.

**It keeps each line of thinking separate.**
- Every question can start a new chat. Chats open as tabs, so you can follow several threads at once, and a reply keeps
  coming in while you read another tab.
- **History** (the clock icon) lists every chat for the analysis, grouped by date. You can search titles, questions
  and answers, and rename or delete chats.
- Chats belong to one analysis. When you switch to another app, the assistant starts fresh with that app's own chats,
  so context never mixes.

**A typical decision flow**

1. Ask a starter question, for example *"Why are users unhappy about login issues?"*
2. Read the cited reviews, and **pin** the ones that make the case.
3. Narrow it down: *"Is this worse for paying users?"* or *"Did it start with version 0.433?"*
4. Turn it into options: *"Write How Might We questions"* or *"What are three ways to fix this, cheapest first?"*
5. Check the ranked **Decisions** list, set the status, and share the **Research report**. It includes your pinned
   quotes.

**Questions people ask**

- *"What should we fix before the next release, and why?"*
- *"What do users love that we must not break in the redesign?"*
- *"Compare new users and long-time users: what frustrates each?"*
- *"Draft a short stakeholder update with the three biggest risks."*
- *"Which complaints get no reply from us, and which should we answer first?"*

The composer keeps you moving. Enter sends, Shift+Enter starts a new line, ↑ brings back your last question and Esc
stops an answer. If the AI provider fails, the error stays in the chat with a **Try again** button.

## A tour of the product

Every analysis has fifteen views in four groups. The app header and the view list stay in place while the content
scrolls.

### Decide
- **Decisions:** ranked fix, redesign, build, reconsider and protect decisions, with evidence, root causes, options, a
  metric to watch and a status.
- **Research report:** method, key findings, user needs, opportunities and recommendations, with quotes. Download it as
  Markdown or print it to PDF.
- **Pinned quotes:** your evidence wall, with notes. Pins go into the report.

![Decisions ranked Now, Next and Later, each with evidence from real reviews](docs/images/decisions.png)

### Understand
- **Overview** and **Problems & priorities,** with a priority matrix (how many people mention each problem against how
  negative they are).
- **Bugs, requests and complaints:** what to fix, what to build, what to redesign and what to reconsider.
- **Journey map, Emotions** (and what each feeling implies), **Segments** (new, long-time and paying users; app
  versions; helpful votes; replied or not), **Risks**, **Accessibility**, **Developer replies** and **Personas.**

![Problems ranked by impact, with a priority matrix](docs/images/problems.png)

![Journey map: an emotional curve across the user journey](docs/images/journey.png)

**Developer replies** show:
- which complaints go unanswered;
- how much of your reply text is copy-paste;
- the most-seen unanswered reviews to reply to first, with an AI draft that fits Google Play's 350-character limit.

![Developer replies: reply rates, copy-paste replies and unanswered complaints](docs/images/replies.png)

### Compare
- **Benchmark** two to four analyses: your app against competitors, two markets or two periods. The AI groups each app's
  themes into shared topics. Leads, lags and lessons are computed from the reviews, each with a quote from both sides.

![Pokémon GO benchmarked against Monster Hunter Now](docs/images/benchmark.png)

### Track and explore
- **Trends & what changed:** sentiment over time, one-star spikes, rising themes, before and after a release.
- **Any period:** the last 7, 30 or 90 days, or a custom range. The app counts the reviews in the period first, so you
  choose how many to analyze.
- **Review explorer:** filter by rating, theme, type, journey stage, emotion, version or text.

### Start in seconds
Pick an app and choose what you want to learn: a health check, what's broken, recent changes or a deep dive. The
market, language and sample size have sensible defaults, which you can adjust.

![Analyze an app: choose a goal instead of filling in a form](docs/images/new-analysis.png)

### A workspace that stays out of the way
- **The sidebar collapses** to a slim icon bar with **⌘\\** (Ctrl+\\ on Windows); icons stay in place.
- **Search your past analyses** by app, developer, country or model. Press **/** to jump to the search box.
- **The assistant panel can be resized:** drag its edge, or double-click to reset.
- **Dark mode,** keyboard-friendly controls and an About page.

## Installation

### What you need
- **Python 3.11 or newer**
- **Node.js 24** (if you use [nvm](https://github.com/nvm-sh/nvm), `nvm use` picks the right version)
- An AI provider: an API key, a ChatGPT Plus/Pro sign-in, an OpenRouter account or a local model in
  [Ollama](https://ollama.com)

### Set it up

```bash
# 1. Get the code
git clone https://github.com/ux-biswarup/google-play-scrapper-for-designers.git
cd google-play-scrapper-for-designers

# 2. Install the backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Build the interface
cd web
nvm use                            # optional, selects Node 24
npm install
npm run build
cd ..

# 4. Start the app
uvicorn backend.main:app --port 8000
```

Open **http://127.0.0.1:8000**.

### First run
1. **Connect an AI model.** Click the AI model item at the bottom of the sidebar (it reads "Connect an AI model" until
   one is set up). You can:
   - paste an API key (Anthropic, OpenAI, Gemini, OpenRouter, Groq, Mistral or any OpenAI-compatible server);
   - choose **Continue with ChatGPT** or **Connect OpenRouter**;
   - point it at Ollama.

   Keys are encrypted on your computer; see [Privacy and security](#privacy-and-security).
2. **Analyze an app.** Click **New analysis**, search for the app or paste its Play Store link, pick a goal and click
   **Start analysis**. The app shows the estimated time and tokens before you start.
3. **Explore and ask.** Open the analysis, browse the views on the left, and click **Ask AI** to start a chat.

Results are stored in `data/app.db` on your computer. To update later, run `git pull`, then
`pip install -r requirements.txt` and `npm install && npm run build` in `web/`, and restart.

Optionally, put fallback keys in a `.env` file: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`,
`OPENROUTER_API_KEY`, `GROQ_API_KEY` or `MISTRAL_API_KEY`. You can preselect a model per provider with `OPENAI_MODEL`
and similar. Keys entered in the app take precedence.

### Troubleshooting
- **The page is blank or says Not Found:** build the interface (`npm run build` in `web/`) before starting the server,
  then restart it.
- **"Address already in use":** another program is using port 8000. Start with `--port 8001` and open that port.
- **An analysis or answer fails:** the error shows the AI provider's own message, for example a wrong key or no
  credits. Fix it in Settings and click **Try again**.

## Use your analyses in Claude, ChatGPT, Cursor and more (MCP)

Review Insights includes an [MCP](https://modelcontextprotocol.io) server. MCP lets AI apps you already use read your
analyses with their own subscription. Ask them to compare apps, pull quotes, write a spec or turn problems into tickets.

**The easiest way:** in the app, open **Use in Claude, ChatGPT…** in the sidebar. It shows copy-paste setup for each
app, with your paths already filled in. The snippets below show the same setup; replace
`/path/to/google-play-scrapper-for-designers` with your folder.

**Claude Desktop.** Go to Settings, Developer, Edit config, add this to `claude_desktop_config.json`, then restart
Claude Desktop:

```json
{
  "mcpServers": {
    "review-insights": {
      "command": "/path/to/google-play-scrapper-for-designers/.venv/bin/python",
      "args": ["-m", "backend.mcp_server"],
      "env": { "PYTHONPATH": "/path/to/google-play-scrapper-for-designers" }
    }
  }
}
```

**Claude Code.** Run this once:

```bash
claude mcp add review-insights --scope user \
  --env PYTHONPATH="/path/to/google-play-scrapper-for-designers" \
  -- "/path/to/google-play-scrapper-for-designers/.venv/bin/python" -m backend.mcp_server
```

**Cursor.** Add this to `~/.cursor/mcp.json`, and keep Review Insights running:

```json
{ "mcpServers": { "review-insights": { "url": "http://localhost:8000/mcp/" } } }
```

**VS Code (Copilot agent mode).** Add this to `.vscode/mcp.json`, and keep Review Insights running:

```json
{ "servers": { "review-insights": { "type": "http", "url": "http://localhost:8000/mcp/" } } }
```

**Codex CLI.** Add this to `~/.codex/config.toml`:

```toml
[mcp_servers.review-insights]
command = "/path/to/google-play-scrapper-for-designers/.venv/bin/python"
args = ["-m", "backend.mcp_server"]
env = { PYTHONPATH = "/path/to/google-play-scrapper-for-designers" }
```

**ChatGPT or claude.ai in the browser.** Web apps can only reach servers on the public internet, so you need a tunnel:
1. Expose the app with a tunnel such as Cloudflare Tunnel or ngrok.
2. Start the app with `MCP_ALLOWED_HOSTS=your-tunnel.example.com uvicorn backend.main:app --port 8000`.
3. Add `https://your-tunnel.example.com/mcp/` as a custom connector. In ChatGPT, that's under Settings, Apps &
   Connectors (developer mode); in claude.ai, under Settings, Connectors.

Stop the tunnel when you're done; anyone with its address can read your analyses.

**What the AI app can do:**
- list your analyses;
- read the overview, problems, journey map, segments, trends, risks, accessibility and developer replies;
- search reviews for quotes;
- compute metrics;
- compare analyses side by side.

**Try asking:**
- *"What are the biggest problems in my latest Pokémon GO analysis?"*
- *"Compare my app with the competitor analyses and list where we lag."*
- *"Write three Jira tickets for the top problems, with quotes as evidence."*

## Privacy and security

- **Runs locally.** Reviews and results stay on your computer (`data/app.db`). Reviews are sent only to the AI provider
  you choose.
- **API keys never live in the browser.** Keys you paste are encrypted by the backend in `data/secrets.enc`. The
  encryption key is kept in your operating system's keychain (macOS Keychain, Windows Credential Manager or Linux
  Secret Service), or in an owner-only file where no keychain exists. The app only shows a masked hint. Choose "this
  session only" to keep a key in memory until the app stops. ChatGPT sign-in tokens are encrypted the same way.
- **Other websites can't use your keys.** The server answers only on local host names and refuses changes requested by
  other websites. App pages use a strict Content-Security-Policy.
- **The MCP endpoint is local only** unless you set `MCP_ALLOWED_HOSTS`.
- **Credentials stay out of git.** `.env` and other credential files are git-ignored. You can install a pre-commit hook
  that blocks committing them: `cp .github/pre-commit-hook.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit`

## FAQ

**Is it free?**
Yes, it's open source under the MIT license. You pay only your AI provider for the tokens you use, or nothing with a
local model or an existing ChatGPT plan. The app estimates the cost before each analysis. Reviews already analyzed with
the same model are reused for free, and the assistant's suggested questions don't use the AI at all.

**How many reviews can it analyze?**
Up to 2,000 per analysis. For a time period, it scans up to 10,000 reviews to count what's there, then you choose how
many to analyze: the newest, or a sample spread across the period.

**Can the assistant make things up?**
It answers from lookups into your analysis and must cite reviews. Citations to reviews that don't exist are removed,
and numbers come from the analysis, not from the model's memory. It only sees the analysis you're in.

**Which languages and countries?**
Any Google Play market and review language. Insights can be written in a different language from the reviews.

**Does it support the Apple App Store?**
Not yet. iOS reviews are next on the roadmap.

**How is this different from a sentiment dashboard?**
Sentiment tells you how people feel. Review Insights tells you what to do about it and how much it matters, and shows
the reviews that prove it.

**Can I share the results?**
Download the research report as Markdown, print any view to PDF, export charts as PNG or SVG, copy pinned quotes or
answers, or connect your team's AI apps through the MCP server.

## Roadmap

- iOS App Store reviews
- Scheduled re-analysis with alerts when a problem spikes
- Exports to Jira, Linear and Notion

## Develop

- **Interface with hot reload:** run `cd web && npm run dev`, then open http://localhost:5173 (it forwards `/api` to the
  backend).
- **API docs:** http://127.0.0.1:8000/docs
- **MCP server:** over stdio with `python -m backend.mcp_server`, or over HTTP at `http://127.0.0.1:8000/mcp/`.
- **Tests:** `pytest` runs offline with no API keys needed. Lint with `ruff check backend tests` and
  `ruff format backend tests`.
- **CI:** runs lint, tests on Python 3.11 to 3.14, the interface build and a smoke test of the running server.

| Folder | What's in it |
| --- | --- |
| `backend/` | FastAPI app, AI providers, analysis pipeline, metrics layer, decision views, benchmarks, assistant (chats, tools, suggestions), MCP server |
| `web/` | React, TypeScript, Vite and Tailwind interface with Plotly charts |
| `tests/unit/` | Offline tests with a fake Play Store and a fake AI model |

## About

Review Insights is made by **[Biswarup Mondal](https://www.biswarupmondal.com)**
([LinkedIn](https://www.linkedin.com/in/biswarup-mondal-aba29461/), [GitHub](https://github.com/ux-biswarup)).
Found a bug or have an idea? [Open an issue](https://github.com/ux-biswarup/google-play-scrapper-for-designers/issues/new).

## License

MIT. See [LICENSE](LICENSE).
