import { useEffect, useRef, useState } from "react";
import type { Config, Data, Layout, PlotMouseEvent } from "plotly.js";
import { useTheme } from "../lib/settings";

type PlotlyModule = typeof import("plotly.js");
type PlotElement = HTMLDivElement & {
  on?: (event: string, handler: (e: PlotMouseEvent) => void) => void;
  removeAllListeners?: (event: string) => void;
};

let plotly: Promise<PlotlyModule> | null = null;
// Plotly is ~4 MB, so it loads only when the first chart is shown.
const loadPlotly = () =>
  (plotly ??= import("plotly.js-dist-min").then((m) => ((m as { default?: PlotlyModule }).default ?? m) as PlotlyModule));

export type ChartColors = { ink: string; muted: string; line: string; neg: string; pos: string; neu: string; hl: string; warn: string };

function readColors(): ChartColors {
  const style = getComputedStyle(document.documentElement);
  const v = (name: string) => style.getPropertyValue(`--${name}`).trim();
  return { ink: v("ink"), muted: v("muted"), line: v("line"), neg: v("neg"), pos: v("pos"), neu: v("neu"), hl: v("hl"), warn: v("warn") };
}

/** Theme colours for building traces; updates when dark mode is toggled. */
export function useChartColors(): ChartColors {
  const { theme } = useTheme();
  const [colors, setColors] = useState(readColors);
  useEffect(() => {
    setColors(readColors());
  }, [theme]);
  return colors;
}

const CONFIG: Partial<Config> = { displayModeBar: false, responsive: true };

export function Plot({
  data,
  layout,
  height = 280,
  label,
  onPointClick,
}: {
  data: Data[];
  layout?: Partial<Layout>;
  height?: number;
  label: string;
  onPointClick?: (event: PlotMouseEvent) => void;
}) {
  const ref = useRef<PlotElement>(null);
  const colors = useChartColors();

  useEffect(() => {
    let cancelled = false;
    loadPlotly().then((Plotly) => {
      const el = ref.current;
      if (cancelled || !el) return;
      const axis = { gridcolor: colors.line, zerolinecolor: colors.line, linecolor: colors.line, tickcolor: colors.line, automargin: true };
      Plotly.react(
        el,
        data,
        {
          height,
          margin: { t: 8, r: 8, b: 8, l: 8 },
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          font: { family: "IBM Plex Sans Variable, sans-serif", size: 12, color: colors.muted },
          hoverlabel: { font: { family: "IBM Plex Sans Variable, sans-serif" } },
          showlegend: false,
          legend: { orientation: "h", y: 1.12, x: 0, font: { color: colors.ink } },
          bargap: 0.35,
          ...layout,
          xaxis: { ...axis, ...layout?.xaxis },
          yaxis: { ...axis, ...layout?.yaxis },
        },
        CONFIG,
      );
      el.removeAllListeners?.("plotly_click");
      if (onPointClick) el.on?.("plotly_click", onPointClick);
    });
    return () => {
      cancelled = true;
    };
  }, [data, layout, height, colors, onPointClick]);

  useEffect(() => {
    const el = ref.current;
    return () => {
      if (el) loadPlotly().then((Plotly) => Plotly.purge(el));
    };
  }, []);

  return <div ref={ref} role="img" aria-label={label} style={{ minHeight: height }} />;
}
