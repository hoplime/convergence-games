import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import _hyperscript from "hyperscript.org";
import htmx from "htmx.org";

declare global {
    interface Window {
        htmx: typeof htmx;
    }
}

const createEditor = (element: Element) => {
    return new Editor({
        element: element,
        extensions: [StarterKit],
        content: "<p>Hello World!</p>",
    });
};

// I know it's ridiculous, but it's fun to bundle htmx and hyperscript with a build step instead of using a CDN
window.htmx = htmx;
_hyperscript.browserInit();

export { createEditor };
