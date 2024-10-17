import { resolve } from "path";
import { defineConfig } from "vite";

export default defineConfig({
    build: {
        emptyOutDir: false,
        outDir: resolve(__dirname, "convergence_games/app/static/js"),
        lib: {
            entry: resolve(__dirname, "convergence_games/app/lib"),
            name: "ConvergenceGames",
            fileName: "lib",
            formats: ["es"],
        },
    },
});
