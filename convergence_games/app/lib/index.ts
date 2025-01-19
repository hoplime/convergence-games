import { Editor, mergeAttributes } from "@tiptap/core";
import BulletList from "@tiptap/extension-bullet-list";
import Color from "@tiptap/extension-color";
// import Document from "@tiptap/extension-document";
import Heading from "@tiptap/extension-heading";
import ListItem from "@tiptap/extension-list-item";
// import ListItem from "@tiptap/extension-list-item";
import OrderedList from "@tiptap/extension-ordered-list";
import Paragraph from "@tiptap/extension-paragraph";
import TextStyle from "@tiptap/extension-text-style";
import Underline from "@tiptap/extension-underline";
import StarterKit from "@tiptap/starter-kit";

// I know it's ridiculous, but it's fun to bundle htmx and hyperscript with a build step instead of using a CDN
import "htmx-ext-preload";
import _hyperscript from "hyperscript.org";

_hyperscript.browserInit();

// TipTap Editor setup
const createColorPicker = (parent_element: Element, editor: Editor) => {
    let color_picker = document.createElement("input");
    color_picker.type = "color";
    color_picker.oninput = (event) => {
        let color = (event.target as HTMLInputElement).value;
        editor.chain().focus().setColor(color).run();
    };
    parent_element.appendChild(color_picker);
    return color_picker;
};

const createEditorButton = (parent_element: Element, label: string, fn: () => void) => {
    let button = document.createElement("button");
    button.className = "rounded-md bg-gray-200 hover:bg-gray-300 px-2 py-1";
    button.innerText = label;
    button.onclick = fn;
    parent_element.appendChild(button);
    return button;
};

const createEditor = (container_element: Element, initial_content: string = "") => {
    // Create the editor and add it to the container
    container_element.className = "border-1 p-1 rounded-md";
    let controls_element = document.createElement("div");
    controls_element.className = "flex flex-row gap-x-2 p-1";
    let editor_element = document.createElement("div");
    editor_element.className = "border-t-1 py-1 px-4";
    container_element.appendChild(controls_element);
    container_element.appendChild(editor_element);

    let editor = new Editor({
        element: editor_element,
        extensions: [
            StarterKit,
            Underline,
            TextStyle,
            Color,
            Paragraph.configure({
                HTMLAttributes: {
                    class: "mb-4",
                },
            }),
            ListItem.configure({
                HTMLAttributes: {
                    class: "ml-6 [&>p]:mb-0",
                },
            }),
            BulletList.configure({
                HTMLAttributes: {
                    class: "list-disc",
                },
            }),
            OrderedList.configure({
                HTMLAttributes: {
                    class: "list-decimal",
                },
            }),
            Heading.configure({
                levels: [1, 2],
            }).extend({
                renderHTML({ node, HTMLAttributes }) {
                    const level = this.options.levels.includes(node.attrs.level)
                        ? node.attrs.level
                        : this.options.levels[0];
                    const classes: { [index: number]: string } = {
                        1: "text-3xl font-bold mb-6",
                        2: "text-xl font-bold mb-4",
                    };
                    return [
                        `h${level}`,
                        mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, { class: `${classes[level]}` }),
                        0,
                    ];
                },
            }),
        ],
        content: initial_content,
        onUpdate: ({ editor }) => {
            let json_content = editor.getJSON();
            console.log(json_content);
        },
    });

    // Create the control buttons
    createColorPicker(controls_element, editor);
    createEditorButton(controls_element, "Bold", () => editor.chain().focus().toggleBold().run());
    createEditorButton(controls_element, "Italic", () => editor.chain().focus().toggleItalic().run());
    createEditorButton(controls_element, "Underline", () => editor.chain().focus().toggleUnderline().run());

    return editor;
};

export { createEditor };
