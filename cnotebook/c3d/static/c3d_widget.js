// C3D anywidget front end: hosts one viewer iframe per widget instance and bridges traits.
// The Python side replaces the quoted sentinel object below, exactly once, with
// {"threeDmol": ..., "gui": ..., "css": ...}. The sentinel is a plain object literal outside any
// comment, so the unsubstituted template stays valid JavaScript for the vitest suite.
const ASSETS = globalThis.__CNOTEBOOK_ASSETS__ || {"__cnotebook_assets__": null};

// Built from a string rather than written as a regular expression literal because U+2028 and
// U+2029 are JavaScript line terminators, so a literal one would end the literal. Keeping this
// file pure ASCII also keeps the Python-side asset substitution byte-safe.
const SCRIPT_UNSAFE = new RegExp("[<>&\\u2028\\u2029]", "g");

/**
 * JSON text safe to inline inside a <script> block (mirrors Python's escape_script_json).
 *
 * The escaping is applied to the serialised JSON text, never to the payload, so the parsed
 * value is unchanged: JSON.parse(escapeScriptJson(v)) deep-equals v. All five characters that
 * can end a script element or a JavaScript line (< > & U+2028 U+2029) are replaced wherever
 * they occur, including inside object keys, each by its own \\uXXXX escape.
 *
 * Whole floats are the one place the two serialisers disagree on text: Python renders 1.0
 * where JSON.stringify renders 1. Both parse to the same number, but a payload that has to be
 * byte-identical on the two sides should carry integers or strings.
 *
 * @param {unknown} value
 * @returns {string}
 */
export function escapeScriptJson(value) {
  return JSON.stringify(value).replace(
    SCRIPT_UNSAFE,
    (ch) => "\\u" + ch.charCodeAt(0).toString(16).padStart(4, "0"),
  );
}

/**
 * Coerce a pixel dimension, rejecting anything that must not reach the style block.
 *
 * The value is interpolated straight into a CSS rule, so a string would be a style-injection
 * vector and NaN, Infinity or a negative number would silently produce a broken container.
 *
 * @param {unknown} value
 * @param {string} name - parameter name, used in the error message
 * @returns {number} the value truncated to whole pixels
 * @throws {TypeError} when the value is not a finite, non-negative number
 */
function pixelDimension(value, name) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new TypeError(`${name} must be a finite, non-negative number, got ${String(value)}`);
  }
  return Math.trunc(value);
}

/**
 * Build the standalone viewer document (same structure as cnotebook.core.viewer3d.render_html).
 *
 * The return value is a raw HTML document, not an attribute value. A caller that mounts it as
 * an iframe srcdoc owns the attribute escaping: assign through the DOM (iframe.srcdoc = html,
 * or setAttribute), or, when building the markup as text, escape it the way cnotebook.c3d does
 * with html.escape. The payload itself carries no < > or &, so molecule data can never close
 * the script element however hostile it is.
 *
 * @param {{threeDmol: string, gui: string, css: string}} assets
 * @param {object|string} payload - init payload object, or already-escaped JSON text
 * @param {number} width
 * @param {number} height
 * @returns {string}
 * @throws {TypeError} when width or height is not a finite, non-negative number
 */
export function buildSrcdoc(assets, payload, width, height) {
  const pixelWidth = pixelDimension(width, "width");
  const pixelHeight = pixelDimension(height, "height");
  const payloadJson = typeof payload === "string" ? payload : escapeScriptJson(payload);
  return [
    "<!DOCTYPE html>",
    '<html lang="en">',
    "<head>",
    '<meta charset="UTF-8">',
    '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
    "<style>",
    assets.css,
    `#app { width: ${pixelWidth}px; height: ${pixelHeight}px; }`,
    "</style>",
    "<script>",
    assets.threeDmol,
    "</script>",
    "</head>",
    "<body>",
    '<div id="app">',
    '  <div id="menubar-container" class="menubar"></div>',
    '  <div id="viewer-container" class="viewer-container"></div>',
    '  <div id="sidebar-container" class="sidebar"></div>',
    '  <div id="terminal-container" class="terminal"></div>',
    "</div>",
    "<script>",
    `window.__C3D_INIT__ = ${payloadJson};`,
    "</script>",
    '<script type="module">',
    assets.gui,
    "</script>",
    "</body>",
    "</html>",
  ].join("\n");
}

export default { render() {} };
