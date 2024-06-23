module.exports = {
    content: ["./convergence_games/app/templates/**/*.html", "./convergence_games/app/templates/**/*.html.jinja"],
    theme: {
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
    safelist: ["text-accent", "alert-info", "alert-success", "alert-warning", "alert-error"],
};
