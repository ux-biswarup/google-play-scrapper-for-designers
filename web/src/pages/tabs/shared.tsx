import { Link, useNavigate } from "react-router";
import { TrendingDown, TrendingUp } from "lucide-react";
import type { Run } from "../../lib/api";
import { Badge, Button, Notice } from "../../components/ui";

/** Shown when a view needs tags that older analyses don't have. */
export function ReanalyzeNotice({ run, what }: { run: Run; what: string }) {
  const navigate = useNavigate();
  return (
    <Notice title={`Run this analysis again to see ${what}`}>
      <p>
        It was made before the app learned to tag severity, user type, reasons for leaving, competitors and accessibility.
        Running it again re-tags the reviews once with your AI model.
      </p>
      <div className="mt-2">
        <Button size="sm" onClick={() => navigate("/new", { state: { rerun: run } })}>
          Run again
        </Button>
      </div>
    </Notice>
  );
}

export function TrendBadge({ trend, goodWhenRising = false }: { trend: string; goodWhenRising?: boolean }) {
  if (trend === "rising")
    return (
      <Badge tone={goodWhenRising ? "pos" : "neg"}>
        <TrendingUp className="size-3" aria-hidden /> Rising
      </Badge>
    );
  if (trend === "falling")
    return (
      <Badge tone={goodWhenRising ? "neg" : "pos"}>
        <TrendingDown className="size-3" aria-hidden /> Falling
      </Badge>
    );
  return null;
}

/** A thin horizontal bar for shares (0-1). */
export function ShareBar({ value, tone = "ink", label }: { value: number; tone?: "ink" | "neg" | "pos" | "muted"; label?: string }) {
  const color = { ink: "bg-ink", neg: "bg-neg", pos: "bg-pos", muted: "bg-muted" }[tone];
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-soft" role="img" aria-label={label ?? `${Math.round(value * 100)}%`}>
      <div className={`h-full ${color}`} style={{ width: `${Math.max(2, Math.min(100, value * 100))}%` }} />
    </div>
  );
}

export function ThemeLink({ theme, children }: { theme: string; children?: React.ReactNode }) {
  return (
    <Link to={`?tab=reviews&theme=${encodeURIComponent(theme)}`} className="hover:underline">
      {children ?? theme}
    </Link>
  );
}

export function SectionIntro({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="mt-1 max-w-prose text-sm text-muted">{children}</p>
    </div>
  );
}
