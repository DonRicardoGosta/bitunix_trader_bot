import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx,js,jsx,mdx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT: "#0b0f17",
          subtle: "#111827",
          card: "#0f1623",
        },
        border: "#1f2937",
        accent: {
          DEFAULT: "#22d3ee",
          subtle: "#0e7490",
        },
        profit: "#16a34a",
        loss: "#dc2626",
        muted: "#94a3b8",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
