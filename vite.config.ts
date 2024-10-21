import { resolve } from "path";
import { defineConfig } from "vite";
import inject from "@rollup/plugin-inject";

export default defineConfig({
    build: {
        emptyOutDir: false,
        outDir: resolve(__dirname, "convergence_games/app/static/js"),
        lib: {
            entry: resolve(__dirname, "convergence_games/app/lib"),
            name: "convergence",
            fileName: "lib",
            formats: ["umd"],
        },
    },
    plugins: [
        inject({
            htmx: "htmx.org",
        }),
    ],
});
