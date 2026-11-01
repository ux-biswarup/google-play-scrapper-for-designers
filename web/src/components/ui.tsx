import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { AlertCircle, ChevronDown, Info, Loader2, Star } from "lucide-react";

const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(" ");

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "brand";
  size?: "sm" | "md";
  busy?: boolean;
};

export function Button({ variant = "secondary", size = "md", busy, className, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-8 px-3 text-sm" : "h-10 px-4",
        variant === "primary" && "bg-ink text-paper hover:opacity-90",
        variant === "secondary" && "border border-line bg-panel text-ink hover:bg-soft",
        variant === "ghost" && "text-muted hover:bg-soft hover:text-ink",
        variant === "danger" && "border border-line bg-panel text-neg hover:bg-soft",
        // Third-party sign-in buttons (black per the provider's guidelines; inverted in dark mode).
        variant === "brand" && "bg-black text-white hover:bg-black/85 dark:bg-white dark:text-black dark:hover:bg-white/85",
        className,
      )}
    >
      {busy && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function Field({ label, hint, htmlFor, children }: { label: string; hint?: ReactNode; htmlFor?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
      </label>
      {children}
      {hint && <p className="text-sm text-muted">{hint}</p>}
    </div>
  );
}

const control =
  "h-10 rounded-md border border-line bg-panel px-3 text-ink placeholder:text-muted focus:border-ink focus:outline-none";
// Full width unless the caller sets its own width class.
const width = (className?: string) => (/(^|\s)w-/.test(className ?? "") ? "" : "w-full");

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={cx(control, width(className), className)} />;
}

/**
 * Native select (keyboard and screen-reader friendly) with the browser's arrow replaced by our own,
 * so it has consistent padding, follows dark mode and looks the same in every browser.
 */
export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  const classes = (className ?? "").split(/\s+/).filter(Boolean);
  const widthClasses = classes.filter((c) => c.startsWith("w-"));
  const otherClasses = classes.filter((c) => !c.startsWith("w-"));
  return (
    <div className={cx("relative", widthClasses.length ? widthClasses.join(" ") : "w-full")}>
      <select
        {...rest}
        className={cx(control, "w-full cursor-pointer appearance-none truncate pr-9", otherClasses.join(" "))}
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden
        className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted"
      />
    </div>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-line bg-panel p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={cx(
            "h-8 rounded px-3 text-sm transition-colors",
            value === option.value ? "bg-ink text-paper" : "text-muted hover:text-ink",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "neg" | "pos" | "warn" }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-medium",
        tone === "neutral" && "bg-soft text-muted",
        tone === "neg" && "bg-neg/12 text-neg",
        tone === "pos" && "bg-pos/12 text-pos",
        tone === "warn" && "bg-warn/12 text-warn",
      )}
    >
      {children}
    </span>
  );
}

export function Notice({ tone = "info", title, children }: { tone?: "info" | "error"; title?: string; children?: ReactNode }) {
  const Icon = tone === "error" ? AlertCircle : Info;
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={cx(
        "flex gap-3 rounded-md border p-3 text-sm",
        tone === "error" ? "border-neg/40 bg-neg/8" : "border-line bg-panel",
      )}
    >
      <Icon className={cx("mt-0.5 size-4 shrink-0", tone === "error" ? "text-neg" : "text-muted")} aria-hidden />
      <div className="flex flex-col gap-1">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className="text-muted">{children}</div>}
      </div>
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-muted" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </div>
  );
}

export function Stars({ value, size = "sm" }: { value: number; size?: "sm" | "md" }) {
  const rounded = Math.round(value);
  return (
    <span className="inline-flex" role="img" aria-label={`${value} out of 5 stars`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          aria-hidden
          className={cx(
            size === "sm" ? "size-3.5" : "size-4",
            i <= rounded ? (rounded <= 2 ? "fill-neg text-neg" : rounded === 3 ? "fill-neu text-neu" : "fill-pos text-pos") : "text-line",
          )}
        />
      ))}
    </span>
  );
}

export function Panel({ title, actions, children, className }: { title?: string; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-lg border border-line bg-panel p-5", className)}>
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-3">
          {title && <h3 className="font-semibold">{title}</h3>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-3 rounded-lg border border-dashed border-line p-8">
      <p className="font-medium">{title}</p>
      {children && <div className="max-w-prose text-sm text-muted">{children}</div>}
      {action}
    </div>
  );
}

export { cx };
