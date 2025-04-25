import FileHandler from "@tiptap-pro/extension-file-handler";
import { Editor, mergeAttributes, generateHTML } from "@tiptap/core";
import BlockQuote from "@tiptap/extension-blockquote";
import BulletList from "@tiptap/extension-bullet-list";
import Color from "@tiptap/extension-color";
import Heading from "@tiptap/extension-heading";
import ImageResize from "tiptap-extension-resize-image";

import ListItem from "@tiptap/extension-list-item";
import OrderedList from "@tiptap/extension-ordered-list";
import Paragraph from "@tiptap/extension-paragraph";
import TextStyle from "@tiptap/extension-text-style";
import Underline from "@tiptap/extension-underline";
import StarterKit from "@tiptap/starter-kit";

const PRESET_COLORS = ["#000000", "#ff0000", "#00ff00", "#0000ff"];

const get_cached_file_contents = (file_path: string) => {
    return fetch(file_path, { cache: "force-cache" }).then((response) => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.text();
    });
};

// TipTap Editor setup
const createColorPicker = (parent_element: Element, icon_path: string, editor: Editor) => {
    let color_picker_container = document.createElement("div");
    color_picker_container.className = "rounded-md px-2 py-1 cursor-pointer hover:bg-base-300";

    // Label
    let color_picker_label = document.createElement("label");
    color_picker_label.className = "flex items-center [&>svg]:w-6 [&>svg]:h-6";
    color_picker_container.appendChild(color_picker_label);

    let color_picker_label_image = document.createElement("svg");
    color_picker_label.appendChild(color_picker_label_image);

    get_cached_file_contents(icon_path).then((resolved_label) => {
        color_picker_label_image.outerHTML = resolved_label;
    });

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

const createEditorButton = (parent_element: Element, icon_path: string, fn: () => void) => {
    let button = document.createElement("button");
    button.className = "rounded-md px-2 py-1 [&>svg]:w-6 [&>svg]:h-6 text-red cursor-pointer hover:bg-base-300";
    get_cached_file_contents(icon_path).then((resolved_label) => {
        button.innerHTML = resolved_label;
    });
    button.onclick = fn;
    button.type = "button";
    parent_element.appendChild(button);
    return button;
};

const editor_extensions = [
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
            const level = this.options.levels.includes(node.attrs.level) ? node.attrs.level : this.options.levels[0];
            const classes: { [index: number]: string } = {
                1: "text-3xl font-bold mt-4",
                2: "text-xl font-bold mt-4",
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
            class: "border-l-4 border-base-content pl-2",
        },
    }),
    ImageResize,
    FileHandler.configure({
        allowedMimeTypes: ["image/png", "image/jpeg", "image/gif", "image/webp"],
        onDrop: (currentEditor, files, pos) => {
            // console.log(files);
            files.forEach((file) => {
                const fileReader = new FileReader();

                fileReader.readAsDataURL(file);
                fileReader.onload = () => {
                    currentEditor
                        .chain()
                        .insertContentAt(pos, {
                            type: "image",
                            attrs: {
                                src: fileReader.result,
                            },
                        })
                        .focus()
                        .run();
                };
            });
        },
        onPaste: (currentEditor, files, htmlContent) => {
            // console.log(files);
            files.forEach((file) => {
                if (htmlContent) {
                    // if there is htmlContent, stop manual insertion & let other extensions handle insertion via inputRule
                    // you could extract the pasted file from this url string and upload it to a server for example
                    // console.log(htmlContent); // eslint-disable-line no-console
                    return false;
                }

                const fileReader = new FileReader();

                fileReader.readAsDataURL(file);
                fileReader.onload = () => {
                    currentEditor
                        .chain()
                        .insertContentAt(currentEditor.state.selection.anchor, {
                            type: "image",
                            attrs: {
                                src: fileReader.result,
                            },
                        })
                        .focus()
                        .run();
                };
            });
        },
    }),
];

const renderEditorContent = (container_element: Element, initial_content_json: string) => {
    let initital_content = initial_content_json ? JSON.parse(initial_content_json) : { type: "doc", content: [] };

    let rendered_content = generateHTML(initital_content, editor_extensions);
    container_element.innerHTML = rendered_content;
};

const createEditor = (
    container_element: Element,
    form_input_name: string,
    initial_content_json: string = "",
    debug: boolean = true,
) => {
    const form_input_id = container_element.id + "_input";

    if (container_element.innerHTML !== "") {
        const current_editor_input = document.getElementById(form_input_id);
        if (current_editor_input !== null) {
            const current_editor_value = (current_editor_input as HTMLInputElement).value;
            initial_content_json = current_editor_value;
        }

        container_element.innerHTML = "";
    }

    // Create the editor and add it to the container
    container_element.className = `text-[1rem] border-1 p-1 rounded-md`;
    let controls_element = document.createElement("div");
    controls_element.className = "flex flex-row flex-wrap gap-x-2 p-1 bg-base-200";
    let editor_element = document.createElement("div");
    editor_element.className = "border-t-1 p-1";
    container_element.appendChild(controls_element);
    container_element.appendChild(editor_element);
    let debug_element = document.createElement("pre");
    if (debug) {
        debug_element.className = "text-xs text-gray-500";
        container_element.appendChild(debug_element);
    }

    let initial_content = initial_content_json ? JSON.parse(initial_content_json) : { type: "doc", content: [] };

    // Create the form input
    let form_input_element = document.createElement("input");
    form_input_element.id = form_input_id;
    form_input_element.type = "hidden";
    form_input_element.name = form_input_name;
    form_input_element.setAttribute("value", JSON.stringify(initial_content));
    container_element.appendChild(form_input_element);

    let editor = new Editor({
        element: editor_element,
        extensions: editor_extensions,
        content: initial_content,
        editorProps: {
            attributes: {
                class: "p-2",
            },
        },
        onUpdate: ({ editor }) => {
            let json_content = editor.getJSON();
            if (debug) {
                console.log(json_content);
                debug_element.innerHTML = JSON.stringify(json_content, null, 2);
            }
            form_input_element.setAttribute("value", JSON.stringify(json_content));
        },
    });

    // Create the control buttons
    createColorPicker(controls_element, "/static/editor/format-color-text.svg", editor);
    createEditorButton(controls_element, "/static/editor/format-header-1.svg", () =>
        editor.chain().focus().setHeading({ level: 1 }).run(),
    );
    createEditorButton(controls_element, "/static/editor/format-header-2.svg", () =>
        editor.chain().focus().setHeading({ level: 2 }).run(),
    );
    createEditorButton(controls_element, "/static/editor/format-paragraph.svg", () =>
        editor.chain().focus().setParagraph().run(),
    );
    createEditorButton(controls_element, "/static/editor/format-bold.svg", () =>
        editor.chain().focus().toggleBold().run(),
    );
    createEditorButton(controls_element, "/static/editor/format-italic.svg", () =>
        editor.chain().focus().toggleItalic().run(),
    );
    createEditorButton(controls_element, "/static/editor/format-underline.svg", () =>
        editor.chain().focus().toggleUnderline().run(),
    );
    createEditorButton(controls_element, "/static/editor/format-strikethrough-variant.svg", () =>
        editor.chain().focus().toggleStrike().run(),
    );
    createEditorButton(controls_element, "/static/editor/format-list-bulleted.svg", () =>
        editor.chain().focus().toggleBulletList().run(),
    );
    createEditorButton(controls_element, "/static/editor/format-list-numbered.svg", () =>
        editor.chain().focus().toggleOrderedList().run(),
    );
    createEditorButton(controls_element, "/static/editor/format-quote-open.svg", () =>
        editor.chain().focus().toggleBlockquote().run(),
    );

    return editor;
};

export { createEditor, renderEditorContent };
