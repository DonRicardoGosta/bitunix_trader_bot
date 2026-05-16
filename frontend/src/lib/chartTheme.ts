/** Recharts tooltip — sötét UI-hoz olvasható színek (ne szürke háttér + fekete szöveg). */
export const CHART_TOOLTIP_STYLE = {
  contentStyle: {
    backgroundColor: "#0f172a",
    border: "1px solid #475569",
    borderRadius: "6px",
    boxShadow: "0 4px 12px rgba(0,0,0,0.35)",
    color: "#e2e8f0",
  },
  labelStyle: {
    color: "#94a3b8",
    fontSize: 11,
    marginBottom: 4,
  },
  itemStyle: {
    color: "#f1f5f9",
    fontSize: 12,
  },
  cursor: { fill: "rgba(148, 163, 184, 0.12)" },
} as const;
