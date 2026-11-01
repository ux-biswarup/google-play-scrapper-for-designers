import { cx } from "./ui";

/** The Review Insights mark: a quotation mark over a highlighter swipe. Same artwork as /logo.svg and the favicon;
 *  the square turns a lighter navy in dark mode so it doesn't disappear into the background. */
export function Logo({ size = 28, className }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 64 64" width={size} height={size} aria-hidden className={cx("shrink-0", className)}>
      <rect width="64" height="64" rx="15" className="fill-[#1a2233] dark:fill-[#2e3747]" />
      <path d="M13 43.6 51.4 42.3 52.8 50.2 14.2 51.4z" fill="#f2d635" />
      <path
        d="M31.5 22.5C31.5 30.3 28.6 35.7 20.2 37.9C25 35.1 27.57 32.5 27.97 28.86A7.5 7.5 0 1 1 31.5 22.5ZM49.5 22.5C49.5 30.3 46.6 35.7 38.2 37.9C43 35.1 45.57 32.5 45.97 28.86A7.5 7.5 0 1 1 49.5 22.5Z"
        fill="#f2f4f7"
      />
    </svg>
  );
}
