import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { buildSrcdoc, escapeScriptJson } from "../../cnotebook/c3d/static/c3d_widget.js";

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
    expect(html).toContain("#app { width: 640px; height: 480px; }");
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

  it("escapes a payload string that was only JSON.stringify'd", () => {
    // The trap: reaching for JSON.stringify instead of escapeScriptJson. Trusting that text
    // would drop a live </script> into the inline script.
    const value = { name: "</script><img src=x onerror=alert(1)>" };
    const html = buildSrcdoc(assets, JSON.stringify(value), 640, 480);
    expect(html).toContain("\\u003c/script\\u003e\\u003cimg src=x onerror=alert(1)\\u003e");
    expect(html.match(/<script/g)).toHaveLength(3);
    expect(html.match(/<\/script>/g)).toHaveLength(3);
    // Escaping raw JSON text gives the same document as escaping the value itself.
    expect(html).toBe(buildSrcdoc(assets, value, 640, 480));
  });

  it("rejects a payload that is neither an object nor non-blank JSON text", () => {
    for (const bad of ["", "   ", "\n\t", null, undefined, 42, true, "".concat()]) {
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

  it("truncates fractional dimensions", () => {
    expect(buildSrcdoc(assets, {}, 640.9, 0)).toContain("#app { width: 640px; height: 0px; }");
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
