import argparse
import json
from pathlib import Path
from typing import Any

import jinjax


def find_textmate_rule_string_position(vscode_settings: str, textmate_rule_name: str) -> tuple[int, int, int] | None:
    # TODO: This is naive, it doesn't handle the textmate rule not existing
    # I just really wanted to keep formatting T.T
    current_object_starts = []
    in_string = False

    for i, char in enumerate(vscode_settings):
        if char == '"':
            in_string = not in_string

        if char == "{" and not in_string:
            current_object_starts.append(i)
        elif char == "}" and not in_string:
            start = current_object_starts.pop()
            # print(f"Found object: {vscode_settings[start : i + 1]}")
            parsed_object: dict[str, Any] = json.loads(vscode_settings[start : i + 1])
            if parsed_object.get("name") == textmate_rule_name:
                # print(f"Found textmate rule: {parsed_object}")
                required_indentation = 0
                j = start - 1
                while vscode_settings[j] == " ":
                    required_indentation += 1
                    j -= 1
                return start, i, required_indentation

    return None


def main(args: argparse.Namespace):
    component_directory: Path = args.component_directory
    file_patterns: list[str] = args.file_patterns
    textmate_rule_name: str = args.textmate_rule_name
    token_color: str = args.token_color
    custom_data_file: Path = args.custom_data_file
    vscode_settings_path: Path = args.vscode_settings_path
    add_vscode_settings: bool = args.add_vscode_settings

    custom_data_tags: list[dict[str, Any]] = []
    component_names: set[str] = set()

    for path in set().union(*(component_directory.rglob(pattern) for pattern in file_patterns)):
        relative_parent = path.parent.relative_to(component_directory).parts
        stem = path.name[: -len("".join(path.suffixes))]
        name = ".".join(relative_parent + (stem,))
        component = jinjax.Component(name=name, path=path)
        print(f"Loaded component: {component.name}")

        required_list = "\n".join([f"  - {arg}" for arg in component.required])
        optional_list = "\n".join([f"  - {arg}" for arg in component.optional])
        custom_data_tags.append(
            {
                "name": component.name,
                "description": {
                    "kind": "markdown",
                    "value": f"**Component:** {component.name}\n\nRequires:\n{required_list}\n\nOptional:\n{optional_list}",
                },
                "references": [{"name": "Source", "url": f"file://{str(path.resolve())}"}],
                "attributes": [
                    {
                        "name": arg,
                        "description": f"Required attribute {arg}",
                    }
                    for arg in component.required
                ]
                + [
                    {
                        "name": arg,
                        "description": f"Optional attribute {arg}",
                    }
                    for arg in component.optional
                ],
            }
        )
        component_names.add(component.name)

    custom_data = {
        "version": 1.1,
        "tags": custom_data_tags,
    }

    with open(custom_data_file, "w") as f:
        json.dump(custom_data, f, indent=4)

    if add_vscode_settings:
        textmate_rule = {
            "scope": [
                f"meta.tag.other.{component_name}.html invalid.illegal.unrecognized-tag.html"
                for component_name in sorted(component_names)
            ],
            "name": textmate_rule_name,
            "settings": {
                "foreground": token_color,
            },
        }

        with open(vscode_settings_path, "r") as f:
            vscode_settings = f.read()
            textmate_rule_start_end = find_textmate_rule_string_position(vscode_settings, textmate_rule_name)
            if textmate_rule_start_end:
                start, end, indent = textmate_rule_start_end
                textmate_rule_str = json.dumps(textmate_rule, indent=4)
                textmate_rule_str = textmate_rule_str.replace("\n", "\n" + " " * indent)
                vscode_settings = vscode_settings[:start] + textmate_rule_str + vscode_settings[end + 1 :]
                with open(vscode_settings_path, "w") as f:
                    f.write(vscode_settings)
            else:
                print("Textmate rule not found")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Component Hinting Helper")
    parser.add_argument("component_directory", type=Path)
    parser.add_argument("--file-patterns", nargs="+", default=["**/*.html.jinja"])
    # Custom Data Output
    parser.add_argument("--custom-data-file", default="jinjax-components.html-data.json")
    # VSCode settings
    parser.add_argument("--add-vscode-settings", action="store_true")
    parser.add_argument("--vscode-settings-path", default=".vscode/settings.json")
    parser.add_argument("--token-color", default="#4EC9B0")
    parser.add_argument("--textmate-rule-name", default="Custom JinjaX Components")
    args = parser.parse_args()

    main(args)
