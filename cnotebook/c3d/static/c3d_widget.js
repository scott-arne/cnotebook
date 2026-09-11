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
 * Apply the script-safe escaping to JSON text that is already serialised.
 *
 * Idempotent: the result is printable ASCII with no <, > or &, so a second pass changes
 * nothing. That is what lets buildSrcdoc accept either a payload object or JSON text without
 * having to trust the caller to have escaped it.
 *
 * The U+2028 and U+2029 arms of SCRIPT_UNSAFE are no-ops after the ASCII pass; they are kept
 * so the escaping stays correct on its own terms, exactly as the Python side keeps them.
 *
 * @param {string} json
 * @returns {string}
 */
function escapeJsonText(json) {
  return json.replace(NON_ASCII, unicodeEscape).replace(SCRIPT_UNSAFE, unicodeEscape);
}

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
 * @param {unknown} value
 * @returns {string}
 */
export function escapeScriptJson(value) {
  return escapeJsonText(JSON.stringify(value));
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
 * A string is escaped rather than trusted. Callers reach for JSON.stringify before they reach
 * for escapeScriptJson, and taking that text as-is would put an unescaped </script> straight
 * into the script element. Because the escaping is idempotent, re-escaping text that was
 * already escaped is free.
 *
 * @param {object|string} payload
 * @returns {string}
 * @throws {TypeError} when the payload is neither an object nor a non-blank string
 */
function resolvePayloadJson(payload) {
  if (typeof payload === "string") {
    if (payload.trim() === "") {
      // An empty string would silently emit `window.__C3D_INIT__ = ;`, a syntax error that
      // takes the whole inline script down.
      throw new TypeError("payload text must not be empty");
    }
    return escapeJsonText(payload);
  }
  if (payload === null || typeof payload !== "object") {
    throw new TypeError(`payload must be an object or JSON text, got ${String(payload)}`);
  }
  return escapeScriptJson(payload);
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
 * @param {object|string} payload - init payload object, or JSON text (escaped either way)
 * @param {number} width
 * @param {number} height
 * @returns {string}
 * @throws {TypeError} when the payload is neither an object nor non-blank JSON text, or when
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
