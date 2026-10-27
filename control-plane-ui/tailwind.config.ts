import type { Config } from "tailwindcss";

/** Full color (hex or oklch) with working opacity modifiers. */
function mix(variable: string) {
  return `color-mix(in srgb, var(${variable}) calc(<alpha-value> * 100%), transparent)`;
}

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: {
          900: mix("--base-900"),
          800: mix("--base-800"),
          700: mix("--base-700"),
          300: mix("--base-300"),
          200: mix("--base-200"),
          100: mix("--base-100"),
          50: mix("--base-50"),
        },
        ink: {
          900: mix("--ink-900"),
          800: mix("--ink-800"),
          700: mix("--ink-700"),
          600: mix("--ink-600"),
          500: mix("--ink-500"),
          400: mix("--ink-400"),
          300: mix("--ink-300"),
        },
        accent: {
          700: mix("--accent-700"),
          600: mix("--accent-600"),
          500: mix("--accent-500"),
          200: mix("--accent-200"),
          100: mix("--accent-100"),
          50: mix("--accent-50"),
        },
        warn: {
          700: mix("--warn-700"),
          600: mix("--warn-600"),
          100: mix("--warn-100"),
          50: mix("--warn-50"),
        },
        danger: {
          700: mix("--danger-700"),
          600: mix("--danger-600"),
          500: mix("--danger-500"),
          200: mix("--danger-200"),
          100: mix("--danger-100"),
          50: mix("--danger-50"),
        },
        primary: mix("--accent-600"),
        "muted-foreground": mix("--ink-500"),
        destructive: mix("--danger-600"),
      },
      boxShadow: {
        panel: "0 10px 30px rgba(15, 20, 25, 0.08)",
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "ui-sans-serif", "system-ui"],
        display: ["IBM Plex Sans", "ui-sans-serif", "system-ui"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      keyframes: {
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        fadeUp: "fadeUp 0.6s ease-out",
      },
    },
  },
  plugins: [],
};

export default config;
