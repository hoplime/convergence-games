import { createEditor } from "./editor";

// I know it's ridiculous, but it's fun to bundle htmx and hyperscript with a build step instead of using a CDN
import "htmx-ext-preload";
import _hyperscript from "hyperscript.org";

_hyperscript.browserInit();

export { createEditor };
