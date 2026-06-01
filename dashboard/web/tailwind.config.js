/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "#0f1419",
        panel: "#1a2332",
        accent: "#e07a5f",
        muted: "#8b9cb3",
      },
    },
  },
  plugins: [],
};
