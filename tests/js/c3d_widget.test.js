import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import widgetModule, {
  buildSrcdoc,
  connectDefault,
  createController,
  escapeScriptJson,
} from "../../cnotebook/c3d/static/c3d_widget.js";

// Paths are resolved from this file rather than with new URL(..., import.meta.url): Vite
// rewrites that static pattern into an asset URL against the happy-dom window location,
// which readFileSync cannot open.
const HERE = dirname(fileURLToPath(import.meta.url));
const MODULE_PATH = join(HERE, "..", "..", "cnotebook", "c3d", "static", "c3d_widget.js");
const vectors = JSON.parse(readFileSync(join(HERE, "fixtures", "script_json_vectors.json"), "utf8"));

describe("the shared fixture", () => {
  it("pins the forbidden set, so dropping one from the fixture fails both suites", () => {
    expect(vectors.forbidden).toEqual([
      "<",
      ">",
      "&",
      String.fromCharCode(0x2028),
      String.fromCharCode(0x2029),
    ]);
  });
});

describe("escapeScriptJson", () => {
  it("matches the shared vectors", () => {
    for (const { input } of vectors.cases) {
      const out = escapeScriptJson(input);
      for (const bad of vectors.forbidden) expect(out).not.toContain(bad);
      expect(JSON.parse(out)).toEqual(input);
    }
  });

  it("agrees byte for byte with the Python escaper", () => {
    // vectors.expected is generated once from the contract and is asserted by the
    // Python suite as well, so a drift in either implementation fails both.
    for (const { input, expected } of vectors.cases) {
      expect(escapeScriptJson(input)).toBe(expected);
    }
  });

  it("escapes forbidden characters in object keys, not just in values", () => {
    const out = escapeScriptJson({ "</script>": "v", "a&b": 1 });
    expect(out).toBe('{"\\u003c/script\\u003e":"v","a\\u0026b":1}');
    expect(JSON.parse(out)).toEqual({ "</script>": "v", "a&b": 1 });
  });

  it("emits pure printable ASCII for every vector", () => {
    // A lone surrogate reaches the payload whenever a molecule name came from os.fsdecode of a
    // non-UTF-8 filename. Anything non-ASCII in the text would make the finished document
    // impossible to encode, so writing it to a file or to an HTTP response would raise.
    for (const { input } of vectors.cases) {
      expect(escapeScriptJson(input)).toMatch(/^[\x20-\x7e]*$/);
    }
  });

  it("escapes a lone surrogate rather than emitting it raw", () => {
    const out = escapeScriptJson({ name: `mol_${String.fromCharCode(0xdce9)}` });
    expect(out).toBe('{"name":"mol_\\udce9"}');
  });

  it("escapes an astral character as the surrogate pair Python writes", () => {
    expect(escapeScriptJson({ e: String.fromCodePoint(0x1f600) })).toBe('{"e":"\\ud83d\\ude00"}');
  });
});

describe("buildSrcdoc", () => {
  const assets = { threeDmol: "/*3d*/", gui: "/*gui*/", css: "body{}" };

  it("inlines assets and the escaped payload in the same structure as the Python renderer", () => {
    const html = buildSrcdoc(assets, { molecules: [{ name: "</script>" }] }, 640, 480);
    expect(html).toContain('<div id="app">');
    expect(html).toContain("#app { width: 100%; height: 100%; }");
    expect(html).toContain("window.__C3D_INIT__ = ");
    expect(html).not.toContain("</script><");
    expect(html).toContain("\\u003c/script\\u003e");
    expect(html.indexOf("/*3d*/")).toBeLessThan(html.indexOf("__C3D_INIT__"));
    expect(html.indexOf("__C3D_INIT__")).toBeLessThan(html.indexOf("/*gui*/"));
  });

  it("keeps a hostile payload inside its script element", () => {
    const hostile = {
      molecules: [{ name: '</script><img src=x onerror=alert(1)>', note: 'a&b" onmouseover="x' }],
    };
    const html = buildSrcdoc(assets, hostile, 640, 480);
    const initLine = html.split("\n").find((line) => line.startsWith("window.__C3D_INIT__ = "));
    for (const bad of vectors.forbidden) expect(initLine).not.toContain(bad);
    // Only the three script elements the builder itself opens may exist.
    expect(html.match(/<script/g)).toHaveLength(3);
    expect(html.match(/<\/script>/g)).toHaveLength(3);
  });

  it("accepts an already-escaped payload string without escaping it twice", () => {
    const payloadJson = escapeScriptJson({ name: "</script>" });
    expect(buildSrcdoc(assets, payloadJson, 640, 480)).toBe(
      buildSrcdoc(assets, { name: "</script>" }, 640, 480),
    );
  });

  it("accepts a payload string that was only JSON.stringify'd", () => {
    // The trap: reaching for JSON.stringify instead of escapeScriptJson. Trusting that text
    // would drop a live </script> into the inline script.
    const value = { name: "</script><img src=x onerror=alert(1)>" };
    const html = buildSrcdoc(assets, JSON.stringify(value), 640, 480);
    expect(html).toContain("\\u003c/script\\u003e\\u003cimg src=x onerror=alert(1)\\u003e");
    expect(html.match(/<script/g)).toHaveLength(3);
    expect(html.match(/<\/script>/g)).toHaveLength(3);
    // Raw JSON text gives the same document as the value itself.
    expect(html).toBe(buildSrcdoc(assets, value, 640, 480));
  });

  it("accepts the Python escaper's output verbatim", () => {
    // The fixture's expected strings are what cnotebook.core.viewer3d.escape_script_json
    // produces, so a document assembled from a Python payload matches the object path.
    for (const { input, expected } of vectors.cases) {
      expect(buildSrcdoc(assets, expected, 640, 480)).toBe(buildSrcdoc(assets, input, 640, 480));
    }
  });

  it("rejects payload text that is not JSON, so it can never be interpolated as code", () => {
    // Escaping alone does not stop this: none of these carry <, > or & , so before the parse
    // step they were copied verbatim after `window.__C3D_INIT__ =` and ran as statements.
    const injections = [
      "{};globalThis.__pwned__=true;//",
      '{"ok":1};globalThis.__pwned__=true;//',
      "1+1",
      "foo",
      '{"a":1} extra',
      "[]",
      "null",
      '"text"',
    ];
    for (const injection of injections) {
      expect(() => buildSrcdoc(assets, injection, 640, 480)).toThrow(TypeError);
      // Nothing from a rejected payload reaches a document, and nothing ran on the way.
      expect(globalThis.__pwned__).toBeUndefined();
    }
  });

  it("rejects a payload that is neither a JSON object nor JSON text of one", () => {
    for (const bad of ["", "   ", "\n\t", null, undefined, 42, true, [], [1, 2]]) {
      expect(() => buildSrcdoc(assets, bad, 640, 480)).toThrow(TypeError);
    }
  });

  it("leaves srcdoc attribute escaping to the host that mounts the iframe", () => {
    // buildSrcdoc returns a raw document: it contains the quotes and slashes of an
    // HTML document, so the mounting code owns the attribute escaping. Assigning
    // through the DOM (or Python's html.escape) is what makes that safe.
    const html = buildSrcdoc(assets, { molecules: [{ name: '"><script>alert(1)</script>' }] }, 640, 480);
    const host = document.createElement("div");
    const frame = document.createElement("iframe");
    frame.setAttribute("srcdoc", html);
    host.appendChild(frame);

    const reparsed = document.createElement("div");
    reparsed.innerHTML = host.innerHTML;
    // Nothing escaped the attribute: still exactly one childless iframe, and the
    // document survives the serialize/parse round trip unchanged.
    expect(reparsed.children).toHaveLength(1);
    expect(reparsed.children[0].tagName).toBe("IFRAME");
    expect(reparsed.children[0].children).toHaveLength(0);
    expect(reparsed.children[0].getAttribute("srcdoc")).toBe(html);
  });

  it("rejects dimensions that are not finite non-negative numbers", () => {
    for (const bad of [Number.NaN, Infinity, -1, "640", null, undefined]) {
      expect(() => buildSrcdoc(assets, {}, bad, 480)).toThrow(TypeError);
      expect(() => buildSrcdoc(assets, {}, 640, bad)).toThrow(TypeError);
    }
    // A rejected width can never reach the style block.
    expect(() => buildSrcdoc(assets, {}, "0}#app{background:url(javascript:1)", 480)).toThrow(TypeError);
  });

  it("bakes no pixel size into the document, whatever size is asked for", () => {
    // The GUI resizes itself from a ResizeObserver on its container. A pixel size written
    // into the document would never change, so the frame would grow while the viewer
    // inside it kept the size it was born with.
    for (const [width, height] of [[640.9, 0], [640, 480], [1, 1]]) {
      const html = buildSrcdoc(assets, {}, width, height);
      expect(html).toContain("html, body { margin: 0; padding: 0; width: 100%; height: 100%; }");
      expect(html).toContain("#app { width: 100%; height: 100%; }");
      expect(html).not.toMatch(/#app \{[^}]*px/);
    }
  });
});

describe("the asset substitution sentinel", () => {
  it("appears exactly once and outside every comment", () => {
    // The Python side rewrites this literal to inline the bundled assets. A second
    // occurrence would be rewritten too, and an occurrence inside the 3Dmol bundle's
    // leading /*! ... */ banner would terminate that comment and break the module.
    const source = readFileSync(MODULE_PATH, "utf8");
    const sentinel = '{"__cnotebook_assets__": null}';
    expect(source.split(sentinel)).toHaveLength(2);

    const before = source.slice(0, source.indexOf(sentinel));
    expect(before.match(/\/\*/g) ?? []).toHaveLength((before.match(/\*\//g) ?? []).length);
    expect(before.slice(before.lastIndexOf("\n"))).not.toContain("//");
  });
});

class FakeModel {
  constructor(state) {
    this.state = { commands: [], command_results: [], view: [], view_origin: "js", view_request: 0, picked: {}, screenshot_request: 0, screenshot: {}, status: "loading", status_message: "", ...state };
    this.handlers = {};
    this.saved = 0;
  }
  get(name) { return this.state[name]; }
  set(name, value) { this.state[name] = value; }
  save_changes() { this.saved += 1; }
  on(event, handler) { (this.handlers[event] ||= []).push(handler); }
  emit(name, value) { this.state[name] = value; (this.handlers[`change:${name}`] || []).forEach((h) => h()); }
}

function fakeApi() {
  const listeners = {};
  return {
    ready: Promise.resolve(),
    executed: [],
    execute(command) { this.executed.push(command); if (command === "boom") throw new Error("nope"); return { ok: true, output: [`ran ${command}`] }; },
    getView() { return [0, 0, 0, 1, 0, 0, 0, 1]; },
    setView(view) { this.lastSet = view; },
    pngDataUrl() { return "data:image/png;base64,QUJD"; },
    on(event, handler) { (listeners[event] ||= []).push(handler); return () => {}; },
    fire(event, payload) { (listeners[event] || []).forEach((h) => h(payload)); },
  };
}

const flush = () => new Promise((r) => setTimeout(r, 0));

describe("createController", () => {
  it("drains commands queued before and after connect, in order, and reports results", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80, commands: [{ id: 1, command: "zoom" }] });
    const api = fakeApi();
    const el = document.createElement("div");
    createController(model, el, { connect: () => Promise.resolve(api) });
    await flush();
    expect(model.get("status")).toBe("ready");
    expect(api.executed).toEqual(["zoom"]);
    expect(model.get("command_results")).toEqual([{ id: 1, ok: true, output: ["ran zoom"] }]);
    const burst = Array.from({ length: 10 }, (_, i) => ({ id: i + 2, command: `c${i + 2}` }));
    model.emit("commands", burst);
    expect(api.executed).toHaveLength(11);
    expect(model.get("command_results").map((r) => r.id)).toEqual(burst.map((c) => c.id));
    model.emit("commands", [{ id: 12, command: "boom" }, { id: 13, command: "ok" }]);
    expect(model.get("command_results")).toEqual([{ id: 12, ok: false, output: ["nope"] }, { id: 13, ok: true, output: ["ran ok"] }]);
  });

  it("answers screenshot requests, forwards picks and views, applies python views", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const api = fakeApi();
    createController(model, document.createElement("div"), { connect: () => Promise.resolve(api) });
    await flush();
    model.emit("screenshot_request", 1);
    expect(model.get("screenshot")).toEqual({ seq: 1, png_base64: "QUJD" });
    api.fire("pick", { atom: { serial: 3 }, modifiers: { shift: true } });
    api.fire("pick", { atom: { serial: 4 }, modifiers: { shift: false } });
    expect(model.get("picked")).toEqual({ seq: 2, atom: { serial: 4 }, modifiers: { shift: false } });
    api.fire("view", [1, 2, 3]);
    expect(model.get("view")).toEqual([1, 2, 3]);
    expect(model.get("view_origin")).toBe("js");
    model.state.view_origin = "python";
    model.state.view = [9, 9, 9];
    model.emit("view_request", 1);
    expect(api.lastSet).toEqual([9, 9, 9]);
  });

  it("applies a view request whose vector the kernel has sent before", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const api = fakeApi();
    await started(model, api);
    model.state.view_origin = "python";
    model.state.view = [9, 9, 9];
    model.emit("view_request", 1);
    expect(api.lastSet).toEqual([9, 9, 9]);

    // The user moves the camera, then the kernel restores the saved view. traitlets sends
    // no `view` change - the value it already holds is the value being set - so only the
    // request counter says anything happened.
    api.lastSet = null;
    model.emit("view_request", 2);
    expect(api.lastSet).toEqual([9, 9, 9]);
  });

  it("ignores a view change that carries no request", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const api = fakeApi();
    await started(model, api);
    // `view` is bidirectional and `view_origin` can already read "python" from an earlier
    // request, so neither is a trigger; only a fresh request number is one.
    model.state.view_origin = "python";
    model.emit("view", [9, 9, 9]);
    expect(api.lastSet).toBe(undefined);
  });

  it("answers the highest screenshot request pending at connect, exactly once", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80, screenshot_request: 1 });
    const api = fakeApi();
    let resolveConnect;
    createController(model, document.createElement("div"), { connect: () => new Promise((resolve) => { resolveConnect = resolve; }) });
    model.emit("screenshot_request", 2);
    expect(model.get("screenshot")).toEqual({});
    resolveConnect(api);
    await flush();
    expect(model.get("screenshot")).toEqual({ seq: 2, png_base64: "QUJD" });
    const saves = model.saved;
    model.emit("screenshot_request", 2);
    expect(model.saved).toBe(saves);
  });

  it("does not re-answer a screenshot already published when a view re-renders", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80, screenshot_request: 3, screenshot: { seq: 3, png_base64: "old" } });
    createController(model, document.createElement("div"), { connect: () => Promise.resolve(fakeApi()) });
    await flush();
    expect(model.get("screenshot")).toEqual({ seq: 3, png_base64: "old" });
  });

  it("reports connection failures through status", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    createController(model, document.createElement("div"), { connect: () => Promise.reject(new Error("no api")) });
    await flush();
    expect(model.get("status")).toBe("error");
    expect(model.get("status_message")).toBe("no api");
  });

  it("creates an iframe with the payload inlined and sized from the model", () => {
    const model = new FakeModel({ payload: '{"molecules":[]}', width: 321, height: 123 });
    const el = document.createElement("div");
    const { iframe } = createController(model, el, { connect: () => new Promise(() => {}) });
    expect(el.contains(iframe)).toBe(true);
    expect(iframe.style.width).toBe("321px");
    expect(iframe.srcdoc).toContain('window.__C3D_INIT__ = {"molecules":[]}');
  });
});

/**
 * Fake host API whose commands finish asynchronously.
 *
 * The real `execute` (spec C1) returns immediately and hands back a `done` promise for a
 * command that is still running; the settle handles let a test decide when that happens.
 */
function asyncFakeApi() {
  const listeners = {};
  return {
    ready: Promise.resolve(),
    executed: [],
    settle: [],
    execute(command) {
      this.executed.push(command);
      const done = new Promise((resolve, reject) => { this.settle.push({ resolve, reject }); });
      return { ok: true, output: [`started ${command}`], done };
    },
    getView() { return [0, 0, 0, 1, 0, 0, 0, 1]; },
    setView(view) { this.lastSet = view; },
    pngDataUrl() { return "data:image/png;base64,QUJD"; },
    on(event, handler) { (listeners[event] ||= []).push(handler); return () => {}; },
    fire(event, payload) { (listeners[event] || []).forEach((h) => h(payload)); },
  };
}

describe("createController with asynchronous commands", () => {
  it("publishes a result only once the command has finished", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80, commands: [{ id: 1, command: "load a" }] });
    const api = asyncFakeApi();
    createController(model, document.createElement("div"), { connect: () => Promise.resolve(api) });
    await flush();
    // The Python handle must settle after the command finished, not when execute returned.
    expect(api.executed).toEqual(["load a"]);
    expect(model.get("command_results")).toEqual([]);
    api.settle[0].resolve();
    await flush();
    expect(model.get("command_results")).toEqual([{ id: 1, ok: true, output: ["started load a"] }]);
  });

  it("runs a command queued during an outstanding one exactly once, after it", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80, commands: [{ id: 1, command: "load a" }] });
    const api = asyncFakeApi();
    createController(model, document.createElement("div"), { connect: () => Promise.resolve(api) });
    await flush();
    model.emit("commands", [{ id: 1, command: "load a" }, { id: 2, command: "load b" }]);
    // The running drain owns the queue: the second command waits rather than racing.
    expect(api.executed).toEqual(["load a"]);
    api.settle[0].resolve();
    await flush();
    expect(api.executed).toEqual(["load a", "load b"]);
    expect(model.get("command_results")).toEqual([{ id: 1, ok: true, output: ["started load a"] }]);
    api.settle[1].resolve();
    await flush();
    expect(model.get("command_results")).toEqual([{ id: 2, ok: true, output: ["started load b"] }]);
  });

  it("reports a rejected command instead of leaving the rejection unhandled", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80, commands: [{ id: 4, command: "load a" }] });
    const api = asyncFakeApi();
    createController(model, document.createElement("div"), { connect: () => Promise.resolve(api) });
    await flush();
    api.settle[0].reject(new Error("file not found"));
    await flush();
    expect(model.get("command_results")).toEqual([{ id: 4, ok: false, output: ["file not found"] }]);
  });
});

describe("createController screenshot capture", () => {
  async function connected(model, pngDataUrl) {
    const api = fakeApi();
    if (pngDataUrl) api.pngDataUrl = pngDataUrl;
    createController(model, document.createElement("div"), { connect: () => Promise.resolve(api) });
    await flush();
    return api;
  }

  it("reports a capture that throws, so Python fails fast instead of timing out", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    await connected(model, () => { throw new Error("no canvas"); });
    model.emit("screenshot_request", 1);
    expect(model.get("screenshot")).toEqual({ seq: 1, error: "no canvas" });
  });

  it("reports a capture that yields no image data", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    await connected(model, () => "data:image/png;base64,");
    model.emit("screenshot_request", 1);
    const answer = model.get("screenshot");
    expect(answer.seq).toBe(1);
    expect(typeof answer.error).toBe("string");
    expect(answer.png_base64).toBeUndefined();
  });

  it("publishes bare base64 that Python can decode with validate=True", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    await connected(model, () => "data:image/png;base64,QUJD\n");
    model.emit("screenshot_request", 1);
    expect(model.get("screenshot")).toEqual({ seq: 1, png_base64: "QUJD" });
  });
});

describe("createController teardown", () => {
  it("detaches the frame and stops answering the model", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const api = fakeApi();
    const el = document.createElement("div");
    const controller = createController(model, el, { connect: () => Promise.resolve(api) });
    await flush();
    const saves = model.saved;
    controller.destroy();
    expect(el.contains(controller.iframe)).toBe(false);
    model.emit("commands", [{ id: 1, command: "zoom" }]);
    model.emit("screenshot_request", 4);
    // The fake's unsubscribe is a no-op, standing in for a host that keeps its listeners.
    api.fire("pick", { atom: { serial: 1 }, modifiers: {} });
    api.fire("view", [4, 5, 6]);
    expect(api.executed).toEqual([]);
    expect(model.saved).toBe(saves);
  });

  it("ignores a connection that resolves after teardown", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    let resolveConnect;
    const controller = createController(model, document.createElement("div"), { connect: () => new Promise((resolve) => { resolveConnect = resolve; }) });
    controller.destroy();
    resolveConnect(fakeApi());
    await flush();
    expect(model.get("status")).toBe("loading");
    expect(model.saved).toBe(0);
  });
});

/**
 * Fake host API that reports view changes the way the GUI does: not while `setView` runs
 * but on its own, 150 ms after the camera settled (spec C1).
 */
function viewFakeApi() {
  const listeners = {};
  return {
    ready: Promise.resolve(),
    executed: [],
    view: [0, 0, 0, 1, 0, 0, 0, 1],
    execute(command) { this.executed.push(command); return { ok: true, output: [] }; },
    getView() { return this.view; },
    setView(view) { this.view = Array.from(view); },
    pngDataUrl() { return "data:image/png;base64,QUJD"; },
    on(event, handler) { (listeners[event] ||= []).push(handler); return () => {}; },
    // The handler gets the host's own array, as the real emitter does, so a test can show
    // that what reaches the trait is a copy.
    report() { (listeners.view || []).forEach((h) => h(this.view)); },
  };
}

/** Fake host API whose unsubscribe functions record that they ran. */
function detachableFakeApi() {
  const listeners = {};
  return {
    ready: Promise.resolve(),
    executed: [],
    subscribed: [],
    unsubscribed: [],
    execute(command) { this.executed.push(command); return { ok: true, output: [] }; },
    getView() { return [0, 0, 0, 1, 0, 0, 0, 1]; },
    setView(view) { this.lastSet = view; },
    pngDataUrl() { return "data:image/png;base64,QUJD"; },
    on(event, handler) {
      this.subscribed.push(event);
      (listeners[event] ||= []).push(handler);
      return () => {
        this.unsubscribed.push(event);
        listeners[event] = listeners[event].filter((h) => h !== handler);
      };
    },
    fire(event, payload) { (listeners[event] || []).forEach((h) => h(payload)); },
  };
}

/** FakeModel with the `off` an anywidget model has, recording what was removed. */
class DetachableFakeModel extends FakeModel {
  constructor(state) {
    super(state);
    this.removed = [];
  }
  off(event, handler) {
    this.removed.push(event);
    this.handlers[event] = (this.handlers[event] || []).filter((h) => h !== handler);
  }
}

/** Connect a controller to a ready api and return once the connection has settled. */
async function started(model, api) {
  const controller = createController(model, document.createElement("div"), {
    connect: () => Promise.resolve(api),
  });
  await flush();
  return controller;
}

describe("createController view echoes", () => {
  it("does not send a python view back when the frame reports it later", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const api = viewFakeApi();
    await started(model, api);
    model.state.view_origin = "python";
    model.state.view = [9, 9, 9];
    model.emit("view_request", 1);
    expect(api.view).toEqual([9, 9, 9]);

    const saves = model.saved;
    api.report();
    // The debounced echo of an applied view is not news, and publishing it would relabel
    // the kernel's own camera as browser-originated.
    expect(model.saved).toBe(saves);
    expect(model.get("view_origin")).toBe("python");

    api.view = [1, 2, 3];
    api.report();
    expect(model.get("view")).toEqual([1, 2, 3]);
    expect(model.get("view_origin")).toBe("js");

    // Suppression is spent once a real change arrives: returning to the kernel's vector
    // by hand is a user action like any other.
    api.view = [9, 9, 9];
    api.report();
    expect(model.get("view")).toEqual([9, 9, 9]);
    expect(model.get("view_origin")).toBe("js");
  });

  it("publishes a copy of the frame's view array", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const api = viewFakeApi();
    await started(model, api);
    api.view = [1, 2, 3];
    api.report();
    api.view[0] = 99;
    // Traits cross the boundary as whole containers; sharing the host's array would let
    // the next camera move rewrite a value the kernel has already been told about.
    expect(model.get("view")).toEqual([1, 2, 3]);
  });

  it("applies a view the kernel set before the frame connected, before capturing", async () => {
    const model = new FakeModel({
      payload: "{}", width: 100, height: 80, commands: [{ id: 1, command: "zoom" }],
      view: [7, 7, 7], view_origin: "python", view_request: 1, screenshot_request: 1,
    });
    const api = viewFakeApi();
    const order = [];
    api.execute = function (command) { order.push("execute"); this.executed.push(command); return { ok: true, output: [] }; };
    api.setView = function (view) { order.push("setView"); this.view = Array.from(view); };
    api.pngDataUrl = function () { order.push("pngDataUrl"); return "data:image/png;base64,QUJD"; };
    await started(model, api);
    // The observer dropped this view (no frame yet) and Python will not resend an
    // identical vector, so the connect drain has to apply it - after the queued commands
    // and before the capture that was waiting for them.
    expect(order).toEqual(["execute", "setView", "pngDataUrl"]);
    expect(api.view).toEqual([7, 7, 7]);
  });

  it("does not re-apply the kernel's view on a later drain", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80, view: [7, 7, 7], view_origin: "python", view_request: 1 });
    const api = viewFakeApi();
    await started(model, api);
    expect(api.view).toEqual([7, 7, 7]);
    // A camera move whose echo has not been debounced yet, then a second command drain:
    // the stale trait must not be pushed back over what the user just did.
    api.view = [1, 2, 3];
    model.emit("commands", [{ id: 1, command: "zoom" }]);
    expect(api.view).toEqual([1, 2, 3]);
  });
});

describe("createController teardown detaches its subscriptions", () => {
  it("removes every host subscription and every trait observer", async () => {
    const model = new DetachableFakeModel({ payload: "{}", width: 100, height: 80 });
    const api = detachableFakeApi();
    const el = document.createElement("div");
    const controller = createController(model, el, { connect: () => Promise.resolve(api) });
    await flush();
    const observed = Object.keys(model.handlers);
    expect(observed).toEqual([
      "change:commands",
      "change:screenshot_request",
      "change:view_request",
      "change:width",
      "change:height",
    ]);
    expect(api.subscribed).toEqual(["pick", "view"]);

    controller.destroy();
    expect(api.unsubscribed).toEqual(["pick", "view"]);
    expect(model.removed).toEqual(observed);
    for (const event of observed) expect(model.handlers[event]).toEqual([]);
    expect(el.contains(controller.iframe)).toBe(false);

    // Nothing can reach the controller any more, so nothing it would publish can either.
    api.fire("pick", { atom: { serial: 1 }, modifiers: {} });
    api.fire("view", [4, 5, 6]);
    model.emit("commands", [{ id: 1, command: "zoom" }]);
    model.emit("screenshot_request", 4);
    expect(api.executed).toEqual([]);
    expect(model.get("picked")).toEqual({});
    expect(model.get("screenshot")).toEqual({});
  });
});

describe("createController protocol shapes", () => {
  it("continues the pick sequence the trait already carries", async () => {
    const model = new FakeModel({
      payload: "{}", width: 100, height: 80, picked: { seq: 5, atom: {}, modifiers: {} },
    });
    const api = fakeApi();
    await started(model, api);
    // A second view of the same model must not restart at 1: traitlets would drop the
    // repeat of a sequence the kernel has already seen.
    api.fire("pick", { atom: { serial: 7 }, modifiers: { shift: true } });
    expect(model.get("picked")).toEqual({ seq: 6, atom: { serial: 7 }, modifiers: { shift: true } });
  });

  it("never publishes a pick with a missing atom or modifiers", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const api = fakeApi();
    await started(model, api);
    // Python drops a pick whose members are not mappings, and a dropped pick is a lost
    // user event.
    api.fire("pick", {});
    expect(model.get("picked")).toEqual({ seq: 1, atom: {}, modifiers: {} });
  });

  it("skips ids that are not integers without adopting them", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const api = fakeApi();
    await started(model, api);
    model.emit("commands", [{ id: "9", command: "string id" }, { id: 1, command: "first" }]);
    expect(api.executed).toEqual(["first"]);
    expect(model.get("command_results")).toEqual([{ id: 1, ok: true, output: ["ran first"] }]);

    const saves = model.saved;
    model.emit("commands", [
      { id: 1.5, command: "fractional id" },
      { id: true, command: "boolean id" },
      { id: null, command: "null id" },
      {},
    ]);
    expect(api.executed).toEqual(["first"]);
    expect(model.saved).toBe(saves);

    // None of them became the high-water mark, so ordinary ids keep flowing.
    model.emit("commands", [{ id: 2, command: "second" }]);
    expect(api.executed).toEqual(["first", "second"]);
  });

  it("runs the lowest unprocessed id first, whatever order the list is in", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const api = fakeApi();
    await started(model, api);
    model.emit("commands", [{ id: 6, command: "sixth" }, { id: 5, command: "fifth" }]);
    // Taking the list in order would run 6 first and then skip 5 as already covered.
    expect(api.executed).toEqual(["fifth", "sixth"]);
    expect(model.get("command_results").map((r) => r.id)).toEqual([5, 6]);
  });

  it("normalises command output to the list of strings Python accepts", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const api = fakeApi();
    api.execute = function (command) {
      this.executed.push(command);
      return command === "numbers" ? { ok: true, output: [1, 2] } : { ok: true };
    };
    await started(model, api);
    // An entry whose output is not a list of strings is dropped by the kernel, which
    // leaves its handle waiting for the full timeout.
    model.emit("commands", [{ id: 1, command: "numbers" }, { id: 2, command: "silent" }]);
    expect(model.get("command_results")).toEqual([
      { id: 1, ok: true, output: ["1", "2"] },
      { id: 2, ok: true, output: [] },
    ]);
  });

  it("mirrors a synchronous failure the host API reports rather than throws", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const api = fakeApi();
    // What src/api.js actually does for a command that fails synchronously: it catches,
    // prints to the terminal and returns ok false with the message appended.
    api.execute = function (command) {
      this.executed.push(command);
      return { ok: false, output: ["partial output", "Unknown selection \"x\""] };
    };
    await started(model, api);
    model.emit("commands", [{ id: 1, command: "zoom x" }]);
    expect(model.get("command_results")).toEqual([
      { id: 1, ok: false, output: ["partial output", "Unknown selection \"x\""] },
    ]);
  });

  it("clears stale error text when a connection succeeds", async () => {
    const model = new FakeModel({
      payload: "{}", width: 100, height: 80, status: "error", status_message: "no api",
    });
    await started(model, fakeApi());
    expect(model.get("status")).toBe("ready");
    expect(model.get("status_message")).toBe("");
  });
});

describe("createController coordinates every view of one model", () => {
  it("does not run a command an earlier view already answered", async () => {
    const model = new FakeModel({
      payload: "{}", width: 100, height: 80,
      commands: [{ id: 1, command: "zoom" }],
      command_results: [{ id: 1, ok: true, output: [] }],
    });
    const api = fakeApi();
    await started(model, api);
    // Python keeps a command in the list until it reads the result, so a view that opens
    // in between sees an entry that is already answered.
    expect(api.executed).toEqual([]);
    model.emit("commands", [{ id: 2, command: "center" }]);
    expect(api.executed).toEqual(["center"]);
  });

  it("does not re-run commands when the same model is rendered again", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80, commands: [{ id: 1, command: "zoom" }] });
    const first = fakeApi();
    const controller = await started(model, first);
    expect(first.executed).toEqual(["zoom"]);

    controller.destroy();
    // Even with the evidence gone from the traits, re-running the command is not allowed:
    // the coordination state belongs to the model, not to the view that happened to run it.
    model.state.command_results = [];
    const second = fakeApi();
    await started(model, second);
    expect(second.executed).toEqual([]);
  });

  it("runs each command in one view only when two views share the model", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const first = fakeApi();
    const second = fakeApi();
    await started(model, first);
    await started(model, second);
    model.emit("commands", [{ id: 1, command: "zoom" }]);
    // Both views see the change. Running the command twice would apply it twice in one
    // frame's terminal and publish two results for one handle.
    expect(first.executed).toEqual(["zoom"]);
    expect(second.executed).toEqual([]);
    expect(model.get("command_results")).toEqual([{ id: 1, ok: true, output: ["ran zoom"] }]);
  });

  it("does not hand a running command to the other view", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const slow = asyncFakeApi();
    const other = fakeApi();
    await started(model, slow);
    await started(model, other);
    model.emit("commands", [{ id: 1, command: "load big.pdb" }]);
    expect(slow.executed).toEqual(["load big.pdb"]);
    expect(other.executed).toEqual([]);

    // A command that has started but not finished is not covered by "answered up to id N",
    // so the claim is what stops the second view taking it while it runs.
    model.emit("commands", [{ id: 1, command: "load big.pdb" }, { id: 2, command: "zoom" }]);
    expect(slow.executed).toEqual(["load big.pdb"]);
    expect(other.executed).toEqual(["zoom"]);
    slow.settle[0].resolve();
    await flush();
    expect(slow.executed).toEqual(["load big.pdb"]);
    expect(model.get("command_results").map((r) => r.id)).toEqual([1]);
  });

  it("gives two views of one model consecutive pick sequences", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const first = fakeApi();
    const second = fakeApi();
    await started(model, first);
    await started(model, second);
    first.fire("pick", { atom: { serial: 1 }, modifiers: {} });
    expect(model.get("picked")).toEqual({ seq: 1, atom: { serial: 1 }, modifiers: {} });
    // The same atom picked in the other view: a repeated sequence would be dropped by
    // traitlets and the second pick would never reach the kernel.
    second.fire("pick", { atom: { serial: 1 }, modifiers: {} });
    expect(model.get("picked")).toEqual({ seq: 2, atom: { serial: 1 }, modifiers: {} });
  });

  it("never publishes a pick sequence the trait has already carried", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const api = fakeApi();
    await started(model, api);
    api.fire("pick", { atom: { serial: 1 }, modifiers: {} });
    expect(model.get("picked")).toEqual({ seq: 1, atom: { serial: 1 }, modifiers: {} });
    // The trait is the record of what the kernel has been told. Whatever moved it on, the
    // next pick has to continue from there rather than from the counter's own idea.
    model.state.picked = { seq: 9, atom: {}, modifiers: {} };
    api.fire("pick", { atom: { serial: 2 }, modifiers: {} });
    expect(model.get("picked")).toEqual({ seq: 10, atom: { serial: 2 }, modifiers: {} });
  });

  it("answers a screenshot request in one view only", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const first = fakeApi();
    const second = fakeApi();
    let captures = 0;
    first.pngDataUrl = () => { captures += 1; return "data:image/png;base64,QUJD"; };
    second.pngDataUrl = () => { captures += 1; return "data:image/png;base64,WFla"; };
    await started(model, first);
    await started(model, second);
    model.emit("screenshot_request", 1);
    // Two captures would race to write the same sequence, and Python would resolve the
    // future with whichever frame published last.
    expect(captures).toBe(1);
    expect(model.get("screenshot")).toEqual({ seq: 1, png_base64: "QUJD" });
  });
});

describe("createController resizing", () => {
  it("resizes the frame and leaves the document fluid", async () => {
    const model = new FakeModel({ payload: "{}", width: 100, height: 80 });
    const { iframe } = await started(model, fakeApi());
    expect(iframe.style.width).toBe("100px");
    model.emit("width", 640);
    model.emit("height", 480);
    expect(iframe.style.width).toBe("640px");
    expect(iframe.style.height).toBe("480px");
    // The GUI tracks its container with a ResizeObserver, so the frame is the only thing
    // with a size: a document that carried its own would never see the change.
    expect(iframe.srcdoc).toContain("#app { width: 100%; height: 100%; }");
    expect(iframe.srcdoc).not.toMatch(/#app \{[^}]*px/);
  });
});

describe("connectDefault", () => {
  /** An iframe in the document, which is what gives happy-dom a contentWindow to reach. */
  function mounted() {
    const iframe = document.createElement("iframe");
    document.body.appendChild(iframe);
    return iframe;
  }

  it("resolves with the host API once the frame has loaded and the GUI is ready", async () => {
    const iframe = mounted();
    const api = { ready: Promise.resolve() };
    iframe.contentWindow.c3d = api;
    const connected = connectDefault(iframe);
    iframe.dispatchEvent(new Event("load"));
    await expect(connected).resolves.toBe(api);
    iframe.remove();
  });

  it("waits for the load event rather than reading the frame straight away", async () => {
    const iframe = document.createElement("iframe");
    let settled = false;
    connectDefault(iframe).then(() => { settled = true; }, () => { settled = true; });
    await flush();
    // A frame that has not loaded has no contentWindow at all, and the GUI defines
    // window.c3d while the document runs: reading eagerly would report a failure for a
    // frame that is merely still booting.
    expect(settled).toBe(false);
  });

  it("rejects when the frame exposes no host API", async () => {
    const iframe = mounted();
    const connected = connectDefault(iframe);
    iframe.dispatchEvent(new Event("load"));
    await expect(connected).rejects.toThrow(/c3d host API/);
    iframe.remove();
  });

  it("rejects when the GUI never becomes ready", async () => {
    const iframe = mounted();
    iframe.contentWindow.c3d = { ready: Promise.reject(new Error("gui boot failed")) };
    const connected = connectDefault(iframe);
    iframe.dispatchEvent(new Event("load"));
    await expect(connected).rejects.toThrow("gui boot failed");
    iframe.remove();
  });
});

describe("the anywidget entry point", () => {
  it("mounts a controller and returns a teardown that detaches it", async () => {
    const model = new DetachableFakeModel({ payload: "{}", width: 100, height: 80 });
    const api = detachableFakeApi();
    const el = document.createElement("div");
    const cleanup = widgetModule.render({ model, el });
    const iframe = el.querySelector("iframe");
    // The mount point stays out of the document so happy-dom never runs the srcdoc: what
    // is under test is the default export's own wiring through connectDefault, with the
    // frame's window standing in for the one the GUI bundle would have populated.
    Object.defineProperty(iframe, "contentWindow", { value: { c3d: api }, configurable: true });
    iframe.dispatchEvent(new Event("load"));
    await flush();
    expect(model.get("status")).toBe("ready");
    expect(api.subscribed).toEqual(["pick", "view"]);

    expect(typeof cleanup).toBe("function");
    cleanup();
    expect(el.querySelector("iframe")).toBe(null);
    expect(api.unsubscribed).toEqual(["pick", "view"]);
    expect(model.removed).toEqual(Object.keys(model.handlers));
    model.emit("commands", [{ id: 1, command: "zoom" }]);
    expect(api.executed).toEqual([]);
  });
});
