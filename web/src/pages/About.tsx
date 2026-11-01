import type { ReactNode } from "react";
import { Bug, ExternalLink, Globe, Star } from "lucide-react";
import { AUTHOR, REPO } from "../lib/author";
import { Logo } from "../components/Logo";

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

/**
 * An illustrated portrait of the author (dark hair, beard, brown jacket), drawn inline instead of a real photo.
 * Works offline and in both themes.
 */
export function AuthorAvatar({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      width={size}
      height={size}
      aria-hidden
      className={`shrink-0 overflow-hidden rounded-full ${className ?? ""}`}
    >
      <circle cx="32" cy="32" r="32" fill="#cfdcec" />
      {/* jacket and shirt */}
      <path d="M8 64c1.5-11 9-17 24-17s22.5 6 24 17z" fill="#8b5a3c" />
      <path d="M25 47.5 32 56l7-8.5c-2-.4-4.4-.6-7-.6s-5 .2-7 .6z" fill="#e9e4dc" />
      <path d="M24.5 47.6 29 64h-4l-4.5-15.2zM39.5 47.6 35 64h4l4.5-15.2z" fill="#6f4530" />
      {/* neck and ears */}
      <path d="M27 40h10v9a5 5 0 0 1-10 0z" fill="#b97d55" />
      <ellipse cx="18.6" cy="30" rx="2.6" ry="3.6" fill="#c68a60" />
      <ellipse cx="45.4" cy="30" rx="2.6" ry="3.6" fill="#c68a60" />
      {/* face */}
      <path d="M19.5 27c0-9 5.6-14.5 12.5-14.5S44.5 18 44.5 27v4.5c0 7.5-5.6 13-12.5 13s-12.5-5.5-12.5-13z" fill="#d29a6e" />
      {/* hair */}
      <path d="M18.6 28.5c-1.8-11 4-18 13.4-18 8 0 14.6 4.6 13.4 18-1.2-5-3.3-8.2-6.4-9.6-3.6 2-9.6 3-15.4 1.6-2.4 1.6-4 4.4-5 8z" fill="#2a211c" />
      {/* beard and moustache */}
      <path d="M19.8 31c.6 8 5.6 13.6 12.2 13.6S43.6 39 44.2 31c-1.4 3.4-3 5.2-5 5.6-1.8-1.6-4.2-2.2-7.2-2.2s-5.4.6-7.2 2.2c-2-.4-3.6-2.2-5-5.6z" fill="#2f2620" />
      <path d="M27.2 36.6c1.4-1.2 3-1.6 4.8-1.6s3.4.4 4.8 1.6c-1.6.4-3.2.6-4.8.6s-3.2-.2-4.8-.6z" fill="#2a211c" />
      <path d="M29.4 39.4c1.6.8 3.6.8 5.2 0" stroke="#e7b48c" strokeWidth="1.2" strokeLinecap="round" fill="none" />
      {/* eyes and brows */}
      <circle cx="26.4" cy="28.4" r="1.5" fill="#2a211c" />
      <circle cx="37.6" cy="28.4" r="1.5" fill="#2a211c" />
      <path d="M23.8 25.2c1.4-1 3.4-1.2 5-.6M35.2 24.6c1.6-.6 3.6-.4 5 .6" stroke="#2a211c" strokeWidth="1.3" strokeLinecap="round" fill="none" />
      {/* nose */}
      <path d="M32 29.5v3.2c0 .6-.6 1-1.4 1" stroke="#b37a52" strokeWidth="1.1" strokeLinecap="round" fill="none" />
    </svg>
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
        <div className="flex items-center gap-3">
          <Logo size={48} />
          <h1 className="text-2xl font-semibold tracking-tight">About Review Insights</h1>
        </div>
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
