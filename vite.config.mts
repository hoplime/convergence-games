import { resolve } from "path";
import { defineConfig } from "vite";

export default defineConfig({
    build: {
        emptyOutDir: false,
        minify: false,
        sourcemap: true,
        outDir: resolve(__dirname, "src/convergence_games/static/js"),
        lib: {
            entry: resolve(__dirname, "src/convergence_games/frontend"),
            name: "convergence",
            fileName: "lib",
            formats: ["umd"],
        },
        rollupOptions: {
            output: {
                entryFileNames: "lib.js",
            },
        },
    },
});
