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

/**
 * Text of a thrown or rejected value, for a status message or a command result line.
 *
 * @param {unknown} err
 * @returns {string}
 */
function errorText(err) {
  return String((err && err.message) || err);
}

/** @param {unknown} value @returns {boolean} whether the value is a thenable */
function isThenable(value) {
  return Boolean(value) && typeof value.then === "function";
}

/**
 * Whether two view arrays hold the same numbers.
 *
 * @param {unknown} a
 * @param {unknown} b
 * @returns {boolean}
 */
function sameView(a, b) {
  return (
    Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((v, i) => v === b[i])
  );
}

/**
 * Default connector: wait for the iframe to load and for the GUI's host API to be ready.
 *
 * @param {HTMLIFrameElement} iframe
 * @returns {Promise<object>} the window.c3d API of the frame
 */
export function connectDefault(iframe) {
  return new Promise((resolve, reject) => {
    iframe.addEventListener(
      "load",
      () => {
        // The frame is same-origin (it is never sandboxed) precisely so this reach into
        // contentWindow works; a sandboxed frame would throw here instead.
        const api = iframe.contentWindow && iframe.contentWindow.c3d;
        if (!api) {
          reject(new Error("c3d host API not found in the viewer frame"));
          return;
        }
        Promise.resolve(api.ready).then(() => resolve(api), reject);
      },
      { once: true },
    );
  });
}

/**
 * Wire one widget model to one viewer iframe.
 *
 * The controller owns every message that crosses the bridge in either direction. Three
 * invariants shape it, all of them forced by the Python side:
 *
 * - Each browser-to-kernel trait carries a sequence number the front end owns and always
 *   increments, because traitlets drops a notification whose value equals the previous one.
 * - The browser-to-kernel traits are declared `echo_update=False`, so a write is never
 *   reflected back; the controller therefore tracks the last command id and the last
 *   answered screenshot sequence itself, seeded from the traits so a second view of the
 *   same model does not redo work the first one already did.
 * - Every published value is a fresh object with the exact shape Python validates, since
 *   a malformed entry is dropped there rather than repaired.
 *
 * @param {object} model - anywidget model (get/set/on/off/save_changes)
 * @param {HTMLElement} el - mount point
 * @param {{connect?: (iframe: HTMLIFrameElement) => Promise<object>}} [options]
 * @returns {{iframe: HTMLIFrameElement, drain: () => void, destroy: () => void, api: object}}
 */
export function createController(model, el, { connect = connectDefault } = {}) {
  const iframe = document.createElement("iframe");
  iframe.style.border = "none";
  iframe.style.width = `${model.get("width")}px`;
  iframe.style.height = `${model.get("height")}px`;

  let api = null;
  let destroyed = false;
  let booted = true;
  let lastProcessedId = 0;
  let draining = false;
  let drainAgain = false;
  let applyingView = false;
  let appliedView = null;
  // Both counters are seeded from the traits, not from zero: a re-rendered view of the same
  // model must not replay a pick sequence or answer a screenshot an earlier view served.
  const lastPick = model.get("picked") || {};
  const lastShot = model.get("screenshot") || {};
  let pickSeq = Number.isInteger(lastPick.seq) ? lastPick.seq : 0;
  let lastScreenshotSeq = Number.isInteger(lastShot.seq) ? lastShot.seq : 0;
  const unsubscribes = [];
  const observers = [];

  /**
   * Write a trait and flush it to the kernel.
   *
   * @param {string} name
   * @param {unknown} value
   */
  function publish(name, value) {
    model.set(name, value);
    model.save_changes();
  }

  /**
   * Report a boot failure through the status pair.
   *
   * @param {unknown} err
   */
  function fail(err) {
    if (destroyed) return;
    model.set("status", "error");
    model.set("status_message", errorText(err));
    model.save_changes();
  }

  /**
   * Subscribe to a trait change, remembering the pair so teardown can undo it.
   *
   * @param {string} name - trait name
   * @param {() => void} handler
   */
  function observe(name, handler) {
    const event = `change:${name}`;
    model.on(event, handler);
    observers.push([event, handler]);
  }

  /**
   * The queued command with the lowest id that has not run yet.
   *
   * Entries are matched by id rather than by position: Python rewrites the whole list as
   * results arrive, so an index is not stable. An id that is not an integer is skipped
   * because Python would drop any result published for it, and adopting it as the
   * high-water mark would break every comparison that follows.
   *
   * @returns {object|null}
   */
  function nextCommand() {
    let next = null;
    for (const cmd of model.get("commands") || []) {
      if (!cmd || !Number.isInteger(cmd.id) || cmd.id <= lastProcessedId) continue;
      if (next === null || cmd.id < next.id) next = cmd;
    }
    return next;
  }

  /**
   * One `command_results` entry in the shape Python validates.
   *
   * @param {number} id
   * @param {unknown} ok
   * @param {unknown} output
   * @returns {{id: number, ok: boolean, output: string[]}}
   */
  function commandResult(id, ok, output) {
    // Python drops an entry whose output is not a list of strings, and a dropped entry
    // leaves its handle outstanding until it times out, so the value is normalised here.
    const lines = Array.isArray(output) ? output.map((line) => String(line)) : [];
    return { id, ok: Boolean(ok), output: lines };
  }

  /**
   * Publish a batch of results, if there are any.
   *
   * @param {Array<object>} results
   */
  function flush(results) {
    if (results.length) publish("command_results", results);
  }

  /**
   * End a drain: publish what it collected and answer a waiting screenshot request.
   *
   * The screenshot is taken here rather than when the request arrived so that a request
   * raised before the frame connected sees the effect of the commands that were queued
   * with it (spec D1: the same after-ready drain answers it).
   *
   * @param {Array<object>} results
   */
  function finish(results) {
    flush(results);
    draining = false;
    if (drainAgain) {
      drainAgain = false;
      drain();
      return;
    }
    answerScreenshot();
  }

  /**
   * Run queued commands until none is left.
   *
   * @param {Array<object>} results - results collected for the next publish
   */
  function pump(results) {
    // A command that finished after teardown resumes here; its model is gone.
    if (destroyed) return;
    for (;;) {
      const cmd = nextCommand();
      if (cmd === null) break;
      // Claim the id before running the command, so neither a re-entrant drain nor the
      // continuation below can run it a second time.
      lastProcessedId = cmd.id;
      let outcome;
      try {
        outcome = api.execute(cmd.command) || {};
      } catch (err) {
        results.push(commandResult(cmd.id, false, [errorText(err)]));
        continue;
      }
      if (isThenable(outcome.done)) {
        // An asynchronous command has only started. Its result waits for the promise so
        // the Python handle settles when the command finished, while the results already
        // collected are published now instead of being held behind it. The rejection arm
        // keeps a failing command from becoming an unhandled rejection; the real host API
        // reports such failures through the terminal and resolves.
        flush(results);
        Promise.resolve(outcome.done).then(
          () => pump([commandResult(cmd.id, outcome.ok, outcome.output)]),
          (err) => pump([commandResult(cmd.id, false, [errorText(err)])]),
        );
        return;
      }
      results.push(commandResult(cmd.id, outcome.ok, outcome.output));
    }
    finish(results);
  }

  /**
   * Run every command that has not run yet, lowest id first.
   *
   * Drains are serialised. A `commands` change that arrives while an asynchronous command
   * is outstanding needs no action, because the running drain re-reads the trait after
   * every step; one that arrives while results are being published schedules a further
   * pass rather than starting a second drain.
   */
  function drain() {
    if (!api || destroyed) return;
    if (draining) {
      drainAgain = true;
      return;
    }
    draining = true;
    pump([]);
  }

  /**
   * Capture the current frame for the `screenshot` trait.
   *
   * @param {number} seq - the request being answered
   * @returns {{seq: number, png_base64: string}|{seq: number, error: string}}
   */
  function capture(seq) {
    let dataUrl;
    try {
      dataUrl = api.pngDataUrl();
    } catch (err) {
      return { seq, error: errorText(err) };
    }
    const marker = "base64,";
    const at = typeof dataUrl === "string" ? dataUrl.indexOf(marker) : -1;
    // Python decodes with validate=True, so the data URL prefix and any wrapping
    // whitespace have to go. A capture that produced no data is reported as a failure
    // rather than as empty bytes, which fails the pending futures now instead of after
    // their timeout.
    const png = at < 0 ? "" : dataUrl.slice(at + marker.length).replace(/\s+/g, "");
    if (!png) return { seq, error: "the viewer produced no PNG data" };
    return { seq, png_base64: png };
  }

  /** Answer the outstanding screenshot request, if there is one and it is new. */
  function answerScreenshot() {
    if (!api || destroyed) return;
    const seq = model.get("screenshot_request") || 0;
    // Requests coalesce: one capture answers every sequence up to the highest one asked
    // for, and Python resolves each future at or below the sequence it gets back.
    if (!Number.isInteger(seq) || seq <= lastScreenshotSeq) return;
    lastScreenshotSeq = seq;
    publish("screenshot", capture(seq));
  }

  /** Apply a view the kernel set, without sending it straight back. */
  function applyPythonView() {
    if (!api || destroyed || model.get("view_origin") !== "python") return;
    const view = model.get("view");
    // Remember what was applied: the GUI reports view changes 150 ms after setView (spec
    // C1), long after the synchronous guard below has been cleared, and that echo would
    // otherwise be published back to the kernel as a browser-originated change.
    appliedView = Array.isArray(view) ? Array.from(view) : null;
    applyingView = true;
    try {
      api.setView(view);
    } finally {
      applyingView = false;
    }
  }

  /**
   * Forward an atom pick to the kernel.
   *
   * @param {{atom: object, modifiers: object}} payload
   */
  function handlePick(payload) {
    if (destroyed) return;
    const event = payload || {};
    pickSeq += 1;
    // Neither member may be null: Python drops a pick whose atom or modifiers is not a
    // mapping, and two identical picks would be delivered once without a new sequence.
    publish("picked", { seq: pickSeq, atom: event.atom || {}, modifiers: event.modifiers || {} });
  }

  /**
   * Forward a view change the user made in the frame.
   *
   * @param {number[]} view
   */
  function handleView(view) {
    if (destroyed || applyingView || sameView(view, appliedView)) return;
    appliedView = null;
    model.set("view_origin", "js");
    model.set("view", Array.from(view));
    model.save_changes();
  }

  /**
   * Take over the connected frame: subscribe to its events and serve what is queued.
   *
   * @param {object} connected - the frame's host API
   */
  function onConnected(connected) {
    // The view can be torn down while the frame is still booting.
    if (destroyed) return;
    api = connected;
    unsubscribes.push(api.on("pick", handlePick), api.on("view", handleView));
    publish("status", "ready");
    // Drains commands queued before display, then answers a screenshot request raised
    // before the frame connected (see finish).
    drain();
  }

  /** Detach every subscription and remove the frame from the document. */
  function destroy() {
    if (destroyed) return;
    destroyed = true;
    for (const unsubscribe of unsubscribes) unsubscribe();
    unsubscribes.length = 0;
    for (const [event, handler] of observers) {
      // anywidget's model exposes Backbone's off. A host model without it keeps its
      // handlers, which is why every handler above checks `destroyed` first.
      if (typeof model.off === "function") model.off(event, handler);
    }
    observers.length = 0;
    iframe.remove();
  }

  try {
    iframe.srcdoc = buildSrcdoc(ASSETS, model.get("payload"), model.get("width"), model.get("height"));
  } catch (err) {
    // A payload that cannot be turned into a document is a boot error. Reporting it
    // through status beats throwing out of render, where the user would get an empty
    // cell and Python would wait out its timeouts.
    booted = false;
    fail(err);
  }
  el.appendChild(iframe);

  observe("commands", drain);
  observe("screenshot_request", answerScreenshot);
  observe("view", applyPythonView);
  observe("width", () => {
    iframe.style.width = `${model.get("width")}px`;
  });
  observe("height", () => {
    iframe.style.height = `${model.get("height")}px`;
  });

  if (booted) connect(iframe).then(onConnected).catch(fail);

  return {
    iframe,
    drain,
    destroy,
    get api() {
      return api;
    },
  };
}

export default {
  /**
   * anywidget entry point: mount one controller per view.
   *
   * The teardown is returned rather than dropped so that re-rendering a cell does not
   * leave an earlier controller subscribed to the same model and answering its requests.
   *
   * @param {{model: object, el: HTMLElement}} view
   * @returns {() => void} cleanup run when the view is destroyed
   */
  render({ model, el }) {
    const controller = createController(model, el);
    return () => controller.destroy();
  },
};
