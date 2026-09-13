import type { Config } from "tailwindcss";

const config: Config = {
  // ThemeContext toggles data-theme explicitly (persisted choice, not
  // prefers-color-scheme) - see globals.css. Most colors re-theme for free
  // via CSS vars, but this lets a `dark:` utility target the same toggle.
  darkMode: ["selector", '[data-theme="dark"]'],
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Every value below is a CSS custom property (see globals.css :root
        // / [data-theme="dark"]), ported from kisan-sathi-frontend.html -
        // never a hardcoded hex. This is what makes dark mode (ThemeContext)
        // work for every existing component with zero className changes.
        soil: {
          50: "var(--surface-2)",
          100: "var(--line)",
          700: "var(--ink-soft)",
          900: "var(--ink)",
        },
        crop: {
          50: "var(--green-100)",
          100: "var(--green-100)",
          500: "var(--green-600)",
          600: "var(--green-700)",
          700: "var(--green-900)",
        },
        marigold: {
          DEFAULT: "var(--marigold)",
          ink: "var(--marigold-ink)",
          100: "var(--marigold-100)",
        },
        sky: {
          DEFAULT: "var(--sky)",
          100: "var(--sky-100)",
        },
        danger: {
          DEFAULT: "var(--danger)",
          100: "var(--danger-100)",
        },
        // Card/modal backgrounds - was hardcoded `bg-white` in several
        // components, which broke dark mode (light text on a white card).
        surface: {
          DEFAULT: "var(--surface)",
          2: "var(--surface-2)",
        },
      },
      fontSize: {
        // Bumped one step: the default 16px body is too small for the
        // target user. Cards use `text-lg` and up throughout.
        base: ["1.0625rem", { lineHeight: "1.6" }],
      },
      fontFamily: {
        // next/font/google variables set on <html> in layout.tsx.
        sans: ["var(--font-noto-sans)", "var(--font-noto-devanagari)", "sans-serif"],
        heading: ["var(--font-baloo)", "var(--font-noto-devanagari)", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
