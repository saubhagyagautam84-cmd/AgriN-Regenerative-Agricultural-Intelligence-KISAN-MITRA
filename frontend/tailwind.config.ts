import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Farmer-facing palette: earth + crop green, high contrast so it
        // stays readable on a cheap phone screen in daylight.
        soil: {
          50: "#faf6f0",
          100: "#f0e6d8",
          700: "#6b4f30",
          900: "#3d2c1a",
        },
        crop: {
          50: "#f2f9ee",
          100: "#dff0d4",
          500: "#4b9b3a",
          600: "#3d8130",
          700: "#2f6625",
        },
      },
      fontSize: {
        // Bumped one step: the default 16px body is too small for the
        // target user. Cards use `text-lg` and up throughout.
        base: ["1.0625rem", { lineHeight: "1.6" }],
      },
    },
  },
  plugins: [],
};

export default config;
