import { Editor, mergeAttributes } from "@tiptap/core";
import BulletList from "@tiptap/extension-bullet-list";
import Color from "@tiptap/extension-color";
import Heading from "@tiptap/extension-heading";
import ListItem from "@tiptap/extension-list-item";
import OrderedList from "@tiptap/extension-ordered-list";
import Paragraph from "@tiptap/extension-paragraph";
import TextStyle from "@tiptap/extension-text-style";
import Underline from "@tiptap/extension-underline";
import StarterKit from "@tiptap/starter-kit";
import BlockQuote from "@tiptap/extension-blockquote";

// I know it's ridiculous, but it's fun to bundle htmx and hyperscript with a build step instead of using a CDN
import "htmx-ext-preload";
import _hyperscript from "hyperscript.org";

_hyperscript.browserInit();

const PRESET_COLORS = ["#000000", "#ff0000", "#00ff00", "#0000ff"];

// TipTap Editor setup
const createColorPicker = (parent_element: Element, editor: Editor) => {
    let color_picker_container = document.createElement("div");
    color_picker_container.className = "rounded-md bg-gray-200 hover:bg-gray-300 px-2 py-1";

    // Label
    let color_picker_label = document.createElement("label");
    color_picker_label.className = "flex items-center";
    color_picker_container.appendChild(color_picker_label);

    let color_picker_label_image = document.createElement("img");
    color_picker_label_image.src = "static/editor/format-color-text.svg";
    color_picker_label_image.className = "w-6 h-6";
    color_picker_label.appendChild(color_picker_label_image);

    // Input
    let color_picker = document.createElement("input");
    color_picker.type = "color";
    color_picker.setAttribute("list", "color-list");
    color_picker.oninput = (event) => {
        let color = (event.target as HTMLInputElement).value;
        editor.chain().focus().setColor(color).run();
    };
    color_picker_label.appendChild(color_picker);

    // Color list
    let color_list = document.createElement("datalist");
    color_list.id = "color-list";
    color_list.innerHTML = PRESET_COLORS.map((color) => `<option value="${color}">`).join("");
    color_picker_label.appendChild(color_list);

    parent_element.appendChild(color_picker_container);

    return color_picker_container;
};

const createEditorButton = (parent_element: Element, label: string, fn: () => void) => {
    let button = document.createElement("button");
    button.className = "rounded-md bg-gray-200 hover:bg-gray-300 px-2 py-1 [&>img]:w-6 [&>img]:h-6";
    button.innerHTML = label;
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
                    class: "mb-2",
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
                        1: "text-3xl font-bold mb-4",
                        2: "text-xl font-bold mb-4",
                    };
                    return [
                        `h${level}`,
                        mergeAttributes(this.options.HTMLAttributes, HTMLAttributes, { class: `${classes[level]}` }),
                        0,
                    ];
                },
            }),
            BlockQuote.configure({
                HTMLAttributes: {
                    class: "border-l-4 border-gray-300 pl-2",
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
    createEditorButton(controls_element, '<img src="static/editor/format-header-1.svg">', () =>
        editor.chain().focus().setHeading({ level: 1 }).run(),
    );
    createEditorButton(controls_element, '<img src="static/editor/format-header-2.svg">', () =>
        editor.chain().focus().setHeading({ level: 2 }).run(),
    );
    createEditorButton(controls_element, '<img src="static/editor/format-paragraph.svg">', () =>
        editor.chain().focus().setParagraph().run(),
    );
    createEditorButton(controls_element, '<img src="static/editor/format-bold.svg">', () =>
        editor.chain().focus().toggleBold().run(),
    );
    createEditorButton(controls_element, '<img src="static/editor/format-italic.svg">', () =>
        editor.chain().focus().toggleItalic().run(),
    );
    createEditorButton(controls_element, '<img src="static/editor/format-underline.svg">', () =>
        editor.chain().focus().toggleUnderline().run(),
    );
    createEditorButton(controls_element, '<img src="static/editor/format-strikethrough-variant.svg">', () =>
        editor.chain().focus().toggleStrike().run(),
    );
    createEditorButton(controls_element, '<img src="static/editor/format-list-bulleted.svg">', () =>
        editor.chain().focus().toggleBulletList().run(),
    );
    createEditorButton(controls_element, '<img src="static/editor/format-list-numbered.svg">', () =>
        editor.chain().focus().toggleOrderedList().run(),
    );
    createEditorButton(controls_element, '<img src="static/editor/format-quote-open.svg">', () =>
        editor.chain().focus().toggleBlockquote().run(),
    );

    return editor;
};

export { createEditor };
