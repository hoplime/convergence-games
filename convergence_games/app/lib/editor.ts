import FileHandler from "@tiptap-pro/extension-file-handler";
import { Editor, mergeAttributes } from "@tiptap/core";
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

// TODO: Fix implementation of ImageResize extension to allow styling and aligning controls
// Fork and PR likely required
// const ImageResizeWithoutAlign = ImageResize.extend({
//     addNodeView() {
//         const originalAddNodeView = ImageResize.config.addNodeView;

//         return (props) => {
//             if (!originalAddNodeView) {
//                 return {
//                     dom: document.createElement("div"),
//                 };
//             }

//             let $original_node_view_renderer = originalAddNodeView.call(this);
//             let $original_node_view = $original_node_view_renderer(props);
//             let $original_wrapper = $original_node_view.dom as HTMLElement;
//             $original_wrapper.children[0].classList.add("[&:nth-child(2)]:hidden");

//             $original_node_view.dom = $original_wrapper;
//             return $original_node_view;
//         };
//     },
// });

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

const createEditor = (container_element: Element, initial_content: string = "", debug: boolean = true) => {
    // Create the editor and add it to the container
    container_element.className = "border-1 p-1 rounded-md";
    let controls_element = document.createElement("div");
    controls_element.className = "flex flex-row gap-x-2 p-1";
    let editor_element = document.createElement("div");
    editor_element.className = "border-t-1 py-1 px-4";
    container_element.appendChild(controls_element);
    container_element.appendChild(editor_element);
    let debug_element = document.createElement("pre");
    if (debug) {
        debug_element.className = "text-xs text-gray-500";
        container_element.appendChild(debug_element);
    }

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
        ],
        content: initial_content,
        onUpdate: ({ editor }) => {
            let json_content = editor.getJSON();
            console.log(json_content);
            debug_element.innerHTML = JSON.stringify(json_content, null, 2);
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
