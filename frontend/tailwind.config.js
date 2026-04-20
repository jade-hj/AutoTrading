/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          900: "#0d1117",
          800: "#161b22",
          700: "#21262d",
          600: "#30363d",
        },
        accent: {
          green:  "#3fb950",
          red:    "#f85149",
          blue:   "#58a6ff",
          yellow: "#e3b341",
        },
      },
    },
  },
  plugins: [],
}

