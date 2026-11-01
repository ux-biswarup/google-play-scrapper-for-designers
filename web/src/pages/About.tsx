import { useState, type ReactNode } from "react";
import { Bug, ExternalLink, Globe, Star } from "lucide-react";
import { AUTHOR, REPO } from "../lib/author";

/** GitHub and LinkedIn marks (Simple Icons, CC0); lucide-react no longer ships brand icons. */
function GithubMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={className}>
      <path d="M12 .3a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2c-3.3.7-4-1.6-4-1.6-.6-1.4-1.4-1.8-1.4-1.8-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.8-1.6-2.7-.3-5.5-1.3-5.5-5.9 0-1.3.5-2.4 1.2-3.2-.1-.3-.5-1.5.1-3.2 0 0 1-.3 3.3 1.2a11.5 11.5 0 0 1 6 0C17.3 4.7 18.3 5 18.3 5c.7 1.7.2 2.9.1 3.2.8.8 1.2 1.9 1.2 3.2 0 4.6-2.8 5.6-5.5 5.9.5.4.9 1.1.9 2.2v3.3c0 .3.2.7.8.6A12 12 0 0 0 12 .3" />
    </svg>
  );
}

function LinkedinMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={className}>
      <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.35V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28zM5.34 7.43a2.06 2.06 0 1 1 0-4.13 2.06 2.06 0 0 1 0 4.13zM7.12 20.45H3.56V9h3.56v11.45zM22.22 0H1.77C.79 0 0 .77 0 1.73v20.54C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.73V1.73C24 .77 23.2 0 22.22 0z" />
    </svg>
  );
}

/** The author's photo, or initials when offline. */
export function AuthorAvatar({ size = 32, className }: { size?: number; className?: string }) {
  const [failed, setFailed] = useState(false);
  const initials = AUTHOR.name
    .split(" ")
    .map((w) => w[0])
    .join("");
  return failed ? (
    <span
      aria-hidden
      style={{ width: size, height: size, fontSize: size * 0.38 }}
      className={`grid shrink-0 place-items-center rounded-full bg-soft font-semibold text-muted ${className ?? ""}`}
    >
      {initials}
    </span>
  ) : (
    <img
      src={AUTHOR.avatar}
      alt=""
      width={size}
      height={size}
      onError={() => setFailed(true)}
      className={`shrink-0 rounded-full border border-line object-cover ${className ?? ""}`}
    />
  );
}

function OutLink({ href, icon, children }: { href: string; icon: ReactNode; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex h-10 items-center gap-2 rounded-md border border-line bg-panel px-4 font-medium hover:bg-soft"
    >
      {icon}
      {children}
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  );
}

export function AboutPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-10 px-6 py-10">
      <header className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">About Review Insights</h1>
        <p className="max-w-prose text-lg leading-relaxed text-muted">
          Review Insights turns Google Play reviews into design and product decisions, with the real reviews behind
          every point. It's free, open source and runs on your computer.
        </p>
      </header>

      <section aria-labelledby="why" className="flex flex-col gap-3">
        <h2 id="why" className="text-lg font-semibold">
          Why it exists
        </h2>
        <div className="flex max-w-prose flex-col gap-3 leading-relaxed">
          <p>
            App reviews are the largest free source of user feedback most teams have, and the least used. Reading
            thousands of them takes days, and sentiment dashboards say how people feel but not what to change.
          </p>
          <p>
            Review Insights was made so designers and product managers can go from reviews to decisions they can
            defend: problems ranked by impact, the moments in the journey where people give up, and the users' own
            words as evidence. The AI writes; the numbers are computed, and every claim links to real reviews.
          </p>
        </div>
      </section>

      <section aria-labelledby="maker" className="flex flex-col gap-4">
        <h2 id="maker" className="text-lg font-semibold">
          Who made it
        </h2>
        <div className="flex flex-col gap-5 rounded-lg border border-line bg-panel p-6 sm:flex-row sm:items-center">
          <AuthorAvatar size={88} />
          <div className="flex flex-col gap-3">
            <div>
              <p className="text-xl font-semibold">{AUTHOR.name}</p>
              <p className="text-muted">{AUTHOR.role}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <OutLink href={AUTHOR.website} icon={<Globe className="size-4" aria-hidden />}>
                Website
              </OutLink>
              <OutLink href={AUTHOR.linkedin} icon={<LinkedinMark className="size-4" />}>
                LinkedIn
              </OutLink>
              <OutLink href={AUTHOR.github} icon={<GithubMark className="size-4" />}>
                GitHub
              </OutLink>
            </div>
          </div>
        </div>
      </section>

      <section aria-labelledby="involved" className="flex flex-col gap-3">
        <h2 id="involved" className="text-lg font-semibold">
          Help make it better
        </h2>
        <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-lg border border-line bg-panel">
          {(
            [
              [`${REPO}/issues/new`, Bug, "Report a problem or suggest a feature", "Opens a GitHub issue"],
              [REPO, Star, "Star the project on GitHub", "It helps other designers and PMs find it"],
              [REPO, ExternalLink, "Read the source code", "MIT license: use it, change it, share it"],
            ] as const
          ).map(([href, Icon, label, hint]) => (
            <li key={label}>
              <a href={href} target="_blank" rel="noreferrer" className="flex items-center gap-3 px-4 py-3 hover:bg-soft">
                <Icon className="size-4 shrink-0 text-muted" aria-hidden />
                <span className="flex-1">
                  <span className="block font-medium">{label}</span>
                  <span className="block text-sm text-muted">{hint}</span>
                </span>
                <span className="sr-only">(opens in a new tab)</span>
              </a>
            </li>
          ))}
        </ul>
      </section>

      <p className="text-sm text-muted">Copyright © 2026 {AUTHOR.name}. Released under the MIT license.</p>
    </div>
  );
}
