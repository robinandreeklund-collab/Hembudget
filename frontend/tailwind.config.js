/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Paper-design (huvud-system)
        paper: "#fbfaf6",
        ink: "#111217",
        rule: "#e7e3d7",
        // Periodic-cell-färger
        "elem-grund": "#eef3ff",
        "elem-fordj": "#fff3e6",
        "elem-expert": "#f3eaff",
        "elem-konto": "#e8f7ef",
        "elem-risk": "#fdecec",
        // Brand-färgerna behålls för bakåtkompat under migreringen
        brand: {
          50: "#f5f7ff",
          100: "#e6eaff",
          500: "#4f46e5",
          600: "#4338ca",
          700: "#3730a3",
        },
      },
      fontFamily: {
        serif: ["Spectral", "Georgia", "serif"],
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      letterSpacing: {
        eyebrow: "0.18em",
      },
    },
  },
  plugins: [],
};
