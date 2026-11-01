import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { MoreHorizontal } from "lucide-react";
import { cx } from "./ui";

export type MenuItem = { label: string; icon?: ReactNode; onSelect: () => void; danger?: boolean };

/** A "More actions" button with a small keyboard-accessible menu (arrows, Home/End, Esc). */
export function MoreMenu({ label = "More actions", items }: { label?: string; items: MenuItem[] }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const button = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const focusItem = (i: number) => {
    const all = list.current?.querySelectorAll<HTMLButtonElement>("[role=menuitem]");
    if (all?.length) all[(i + all.length) % all.length].focus();
  };

  useEffect(() => {
    if (!open) return;
    focusItem(0);
    const onDown = (e: MouseEvent) => {
      if (!list.current?.contains(e.target as Node) && !button.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const close = () => {
    setOpen(false);
    button.current?.focus();
  };

  return (
    <div className="relative">
      <button
        ref={button}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        aria-label={label}
        title={label}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setOpen(true);
          }
        }}
        className={cx(
          "grid size-8 place-items-center rounded-md border border-line bg-panel text-muted hover:bg-soft hover:text-ink",
          open && "bg-soft text-ink",
        )}
      >
        <MoreHorizontal className="size-4" aria-hidden />
      </button>
      {open && (
        <div
          ref={list}
          id={id}
          role="menu"
          aria-label={label}
          onKeyDown={(e) => {
            const all = [...(list.current?.querySelectorAll<HTMLButtonElement>("[role=menuitem]") ?? [])];
            const i = all.indexOf(document.activeElement as HTMLButtonElement);
            if (e.key === "Escape") {
              e.preventDefault();
              close();
            } else if (e.key === "ArrowDown") {
              e.preventDefault();
              focusItem(i + 1);
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              focusItem(i - 1);
            } else if (e.key === "Home") {
              e.preventDefault();
              focusItem(0);
            } else if (e.key === "End") {
              e.preventDefault();
              focusItem(-1);
            } else if (e.key === "Tab") {
              setOpen(false);
            }
          }}
          className="absolute top-full right-0 z-30 mt-1 min-w-44 rounded-lg border border-line bg-panel p-1 shadow-lg"
        >
          {items.map((item) => (
            <button
              key={item.label}
              type="button"
              role="menuitem"
              tabIndex={-1}
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
              className={cx(
                "flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm focus:bg-soft focus:outline-none",
                item.danger ? "text-neg hover:bg-soft" : "text-ink hover:bg-soft",
              )}
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
