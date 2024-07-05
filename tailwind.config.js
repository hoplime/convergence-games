const { default: daisyui } = require("daisyui");
const defaultTheme = require("tailwindcss/defaultTheme");

const theme_overrides = {
    primary: "#d3c5db",
    accent: "#a64253",
};

module.exports = {
    content: ["./convergence_games/app/templates/**/*.html", "./convergence_games/app/templates/**/*.html.jinja"],
    theme: {
        fontFamily: {
            header: ['"Josefin Sans"', ...defaultTheme.fontFamily.sans],
            sans: ['"Open Sans"', ...defaultTheme.fontFamily.sans],
        },
        extend: {
            screens: {
                "-2xl": { max: "1535px" },
                // => @media (max-width: 1535px) { ... }

                "-xl": { max: "1279px" },
                // => @media (max-width: 1279px) { ... }

                "-lg": { max: "1023px" },
                // => @media (max-width: 1023px) { ... }

                "-md": { max: "767px" },
                // => @media (max-width: 767px) { ... }

                "-sm": { max: "639px" },
                // => @media (max-width: 639px) { ... }
            },
        },
    },
    plugins: [require("daisyui")],
    safelist: [
        "text-accent",
        "alert-info",
        "alert-success",
        "alert-warning",
        "alert-error",
        // Dynamic Grids for Dropdowns :/
        "grid-cols-1",
        "md:w-[12rem]",
        "grid-cols-2",
        "md:w-[24rem]",
        "grid-cols-3",
        "md:w-[36rem]",
        "grid-cols-4",
        "md:w-[48rem]",
    ],
    darkMode: ["selector", '[data-theme="dark"]'],
    daisyui: {
        themes: [
            {
                light: {
                    ...require("daisyui/src/theming/themes")["light"],
                    ...theme_overrides,
                },
                dark: {
                    ...require("daisyui/src/theming/themes")["dark"],
                    ...theme_overrides,
                },
            },
        ],
    },
};
