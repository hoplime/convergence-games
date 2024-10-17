import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";

const createEditor = (element: Element) => {
    return new Editor({
        element: element,
        extensions: [StarterKit],
        content: "<p>Hello World!</p>",
    });
};

export { createEditor };
