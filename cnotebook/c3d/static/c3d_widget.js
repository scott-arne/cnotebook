// C3D anywidget front end: hosts one viewer iframe per widget instance and bridges traits.
// The Python side replaces the quoted sentinel object below, exactly once, with
// {"threeDmol": ..., "gui": ..., "css": ...}. The sentinel is a plain object literal outside any
// comment, so the unsubstituted template stays valid JavaScript for the vitest suite.
const ASSETS = globalThis.__CNOTEBOOK_ASSETS__ || {"__cnotebook_assets__": null};

// Both patterns are built from strings rather than written as regular expression literals
// because U+2028 and U+2029 are JavaScript line terminators, so a literal one would end the
// literal. Keeping this file pure ASCII also keeps the Python-side asset substitution byte-safe.
//
// NON_ASCII replicates Python's json.dumps(ensure_ascii=True). Measured against CPython, the
// two serialisers already agree below U+007F: JSON.stringify emits the same \b \t \n \f \r
// short forms and the same lowercase \u00XX escapes for the other C0 controls, and both escape
// lone surrogates as \udXXX. The only code units left to escape are therefore U+007F and above.
// The pattern deliberately has no `u` flag so it matches surrogate code units one at a time,
// which turns an astral character into the two surrogate escapes that Python also writes.
const NON_ASCII = new RegExp("[\\u007f-\\uffff]", "g");
const SCRIPT_UNSAFE = new RegExp("[<>&\\u2028\\u2029]", "g");

/** @param {string} ch @returns {string} the code unit as a lowercase \\uXXXX escape */
const unicodeEscape = (ch) => "\\u" + ch.charCodeAt(0).toString(16).padStart(4, "0");

/**
 * JSON text safe to inline inside a <script> block (mirrors Python's escape_script_json).
 *
 * The escaping is applied to the serialised JSON text, never to the payload, so the parsed
 * value is unchanged: JSON.parse(escapeScriptJson(v)) deep-equals v. All five characters that
 * can end a script element or a JavaScript line (< > & U+2028 U+2029) are replaced wherever
 * they occur, including inside object keys, and the output is pure ASCII so it can always be
 * encoded, even when a molecule name carries a lone surrogate.
 *
 * Byte-identity with Python holds for payloads whose numbers are integers or strings and whose
 * object keys are not integer-like. The two known divergences: Python writes a whole float as
 * 1.0 where JSON.stringify writes 1, and JavaScript reorders array-index keys ("0", "1", ...)
 * to the front of an object where Python preserves insertion order.
 *
 * The U+2028 and U+2029 arms of SCRIPT_UNSAFE are no-ops after the ASCII pass; they are kept
 * so the escaping stays correct on its own terms, exactly as the Python side keeps them.
 *
 * @param {unknown} value
 * @returns {string}
 */
export function escapeScriptJson(value) {
  return JSON.stringify(value).replace(NON_ASCII, unicodeEscape).replace(SCRIPT_UNSAFE, unicodeEscape);
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
 * Resolve the payload argument to escaped JSON text.
 *
 * Caller text is never interpolated. Escaping alone is not a defence here: it only rewrites
 * characters that matter to HTML, so text such as `{};globalThis.pwned=true;//` passes through
 * untouched and executes as statements after `window.__C3D_INIT__ =`. Parsing the string and
 * re-serialising the parsed value is what makes the assignment a value rather than caller
 * code, and the object shape check keeps `null`, arrays and bare literals out: the init payload
 * is always a JSON object.
 *
 * @param {object|string} payload - payload object, or JSON text of an object
 * @returns {string}
 * @throws {TypeError} when the payload is blank, is not valid JSON, or is not a JSON object
 */
function resolvePayloadJson(payload) {
  let value = payload;
  if (typeof payload === "string") {
    if (payload.trim() === "") {
      // An empty string would silently emit `window.__C3D_INIT__ = ;`, a syntax error that
      // takes the whole inline script down.
      throw new TypeError("payload text must not be empty");
    }
    try {
      value = JSON.parse(payload);
    } catch (cause) {
      throw new TypeError(`payload text is not valid JSON: ${cause.message}`);
    }
  }
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    const kind = value === null ? "null" : Array.isArray(value) ? "array" : typeof value;
    throw new TypeError(`payload must be a JSON object, got ${kind}`);
  }
  return escapeScriptJson(value);
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
 * A string payload is JSON text of an object. The module parses it and re-serialises the
 * parsed value, so byte-identity with the caller's text is not promised - floats and
 * integer-like keys can come back differently - while the escaping guarantees above are. Text
 * that is not JSON, or JSON that is not an object, is rejected rather than interpolated.
 *
 * @param {{threeDmol: string, gui: string, css: string}} assets
 * @param {object|string} payload - init payload object, or JSON text of one
 * @param {number} width
 * @param {number} height
 * @returns {string}
 * @throws {TypeError} when the payload is not a JSON object or JSON text of one, or when
 *   width or height is not a finite, non-negative number
 */
export function buildSrcdoc(assets, payload, width, height) {
  const pixelWidth = pixelDimension(width, "width");
  const pixelHeight = pixelDimension(height, "height");
  const payloadJson = resolvePayloadJson(payload);
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
