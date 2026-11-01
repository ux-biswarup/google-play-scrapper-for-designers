import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { cx } from "./ui";

const MIN = 320;
const DEFAULT = 416; // 26rem
const MAIN_MIN = 480; // always leave this much room for the analysis
const HARD_MAX = 960;
const STEP = 24;

const maxFor = (viewport: number) => Math.max(MIN, Math.min(HARD_MAX, viewport - MAIN_MIN));
const clamp = (value: number, viewport: number) => Math.min(Math.max(value, MIN), maxFor(viewport));

/** Width of a right-hand side panel, remembered across visits and kept within the window. */
export function usePanelWidth(key: string): [number, (width: number) => void, { min: number; max: number; reset: () => void }] {
  const [stored, setStored] = useState(() => Number(localStorage.getItem(key)) || DEFAULT);
  const [viewport, setViewport] = useState(() => window.innerWidth);
  useEffect(() => {
    const onResize = () => setViewport(window.innerWidth);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  const set = useCallback(
    (width: number) => {
      const next = Math.round(clamp(width, window.innerWidth));
      setStored(next);
      localStorage.setItem(key, String(next));
    },
    [key],
  );
  return [clamp(stored, viewport), set, { min: MIN, max: maxFor(viewport), reset: () => set(DEFAULT) }];
}

/**
 * Drag handle on the left edge of a right-hand panel. Pointer drag, arrow keys (Home/End for min/max) and
 * double-click to reset. Exposed to assistive tech as a vertical separator with its current width.
 */
export function ResizeHandle({
  width,
  onResize,
  min,
  max,
  onReset,
  label,
}: {
  width: number;
  onResize: (width: number) => void;
  min: number;
  max: number;
  onReset: () => void;
  label: string;
}) {
  const start = useRef<{ x: number; width: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    start.current = { x: e.clientX, width };
    setDragging(true);
    // Keep the resize cursor and stop text selection while dragging over the page.
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!start.current) return;
    // The panel is on the right, so dragging left makes it wider.
    onResize(start.current.width + (start.current.x - e.clientX));
  };
  const end = () => {
    start.current = null;
    setDragging(false);
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  };
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? STEP * 4 : STEP;
    const next =
      e.key === "ArrowLeft" ? width + step : e.key === "ArrowRight" ? width - step : e.key === "Home" ? min : e.key === "End" ? max : null;
    if (next === null) return;
    e.preventDefault();
    onResize(next);
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      title="Drag to resize, double-click to reset"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={end}
      onPointerCancel={end}
      onLostPointerCapture={end}
      onDoubleClick={onReset}
      onKeyDown={onKeyDown}
      className="group absolute inset-y-0 -left-1.5 z-10 hidden w-3 cursor-col-resize touch-none justify-center focus-visible:outline-none lg:flex"
    >
      <span
        aria-hidden
        className={cx(
          "h-full w-0.5 transition-colors",
          dragging ? "bg-ink" : "bg-transparent group-hover:bg-ink/30 group-focus-visible:bg-ink",
        )}
      />
    </div>
  );
}
