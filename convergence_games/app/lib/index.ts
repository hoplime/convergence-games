import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";

// I know it's ridiculous, but it's fun to bundle htmx and hyperscript with a build step instead of using a CDN
import _hyperscript from "hyperscript.org";
import "htmx-ext-preload";

_hyperscript.browserInit();

const createEditor = (element: Element) => {
    return new Editor({
        element: element,
        extensions: [StarterKit],
        content: "<p>Hello World!</p>",
    });
};

export { createEditor };
