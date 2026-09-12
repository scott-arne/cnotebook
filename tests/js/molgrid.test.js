import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { beforeEach, describe, expect, it, vi } from "vitest";
import widgetModule, { StaticModel, applyFilters, createGrid, resolveTheme, sortItems } from "../../cnotebook/grid/static/molgrid.js";

// Paths are resolved from this file rather than with new URL(..., import.meta.url): Vite
// rewrites that static pattern into an asset URL against the happy-dom window location,
// which readFileSync cannot open.
const HERE = dirname(fileURLToPath(import.meta.url));
const MODULE_PATH = join(HERE, "..", "..", "cnotebook", "grid", "static", "molgrid.js");
const STYLE_PATH = join(HERE, "..", "..", "cnotebook", "grid", "static", "molgrid.css");

class FakeModel {
  constructor(state) {
    this.state = { revision: 0, visible: [], images: {}, selection: [], smarts_request: {}, smarts_result: {}, error: "", ...state };
    this.handlers = {};
  }
  get(name) { return this.state[name]; }
  set(name, value) { this.state[name] = value; }
  save_changes() {}
  on(event, handler) { (this.handlers[event] ||= []).push(handler); }
  // Backbone's off, which is what anywidget's model exposes and what teardown has to call.
  off(event, handler) {
    const list = this.handlers[event] || [];
    const at = list.indexOf(handler);
    if (at >= 0) list.splice(at, 1);
  }
  emit(name, value) { this.state[name] = value; [...(this.handlers[`change:${name}`] || [])].forEach((h) => h()); }
}

/** @returns {number} how many handlers the model is holding, over every event */
function handlerCount(model) {
  return Object.values(model.handlers).reduce((total, list) => total + list.length, 0);
}

const items = Array.from({ length: 5 }, (_, i) => ({
  i, title: i === 0 ? "<img src=x onerror=alert(1)>" : `mol${i}`, smiles: "C".repeat(i + 1),
  fields: { MW: String(10 * (5 - i)), Name: `name${i}` }, badges: [`MW: ${10 * (5 - i)}`], cluster: i % 2 ? "odd" : "even",
}));
const config = { page_size: 2, sort_by: null, badges: ["MW"], search_fields: ["Name"], info_fields: ["MW", "Name"], export_columns: ["MW", "Name"],
  cluster_labels: ["even", "odd"], cluster_counts: true, theme: "light", static: false, select: true, information: true, title: true, image_width: 100, image_height: 80 };

function mount(overrides = {}, itemList = items) {
  const model = new FakeModel({ items: itemList, config: { ...config, ...overrides }, images: { 0: "<svg id='img0'></svg>" } });
  const el = document.createElement("div");
  document.body.appendChild(el);
  const grid = createGrid(model, el);
  return { model, el, grid };
}

describe("pure helpers", () => {
  it("filters by text, cluster and smarts matches", () => {
    expect(applyFilters(items, { query: "name3", mode: "properties", clusters: new Set(), smartsMatches: null }).map((i) => i.i)).toEqual([3]);
    expect(applyFilters(items, { query: "", mode: "properties", clusters: new Set(["odd"]), smartsMatches: null }).map((i) => i.i)).toEqual([1, 3]);
    expect(applyFilters(items, { query: "", mode: "smarts", clusters: new Set(), smartsMatches: new Set([4]) }).map((i) => i.i)).toEqual([4]);
  });
  it("sorts numerically and by string", () => {
    expect(sortItems(items, { field: "MW", descending: false }).map((i) => i.i)).toEqual([4, 3, 2, 1, 0]);
    expect(sortItems(items, { field: "Name", descending: true })[0].i).toBe(4);
  });
  it("resolves theme", () => {
    const el = document.createElement("div");
    expect(resolveTheme("dark", el)).toBe("dark");
    expect(["light", "dark"]).toContain(resolveTheme("auto", el));
  });
  it("resolves an explicit theme without consulting the document, and auto from its luminance", () => {
    // An explicit theme has to win even when the host document says otherwise, because it is
    // the user's own setting; auto is the only mode that reads the lab theme variable.
    const el = document.createElement("div");
    const host = el.ownerDocument.documentElement;
    host.style.setProperty("--jp-layout-color1", "#111111");
    try {
      expect(resolveTheme("light", el)).toBe("light");
      expect(resolveTheme("dark", el)).toBe("dark");
      expect(resolveTheme("auto", el)).toBe("dark");
      host.style.setProperty("--jp-layout-color1", "#ffffff");
      expect(resolveTheme("auto", el)).toBe("light");
      host.style.setProperty("--jp-layout-color1", "not a colour");
      expect(["light", "dark"]).toContain(resolveTheme("auto", el));
    } finally {
      host.style.removeProperty("--jp-layout-color1");
    }
    // Without the variable the media query decides, and either answer is legitimate.
    expect(["light", "dark"]).toContain(resolveTheme("auto", el));
  });
});

describe("grid controller", () => {
  beforeEach(() => { document.body.innerHTML = ""; });

  it("renders the first page, publishes visible indices, and shows images when they arrive", () => {
    const { model, el } = mount();
    expect(el.querySelectorAll(".cn-molgrid-card")).toHaveLength(2);
    expect(model.get("visible")).toEqual([0, 1, 2, 3]);
    expect(el.querySelector("#img0")).not.toBeNull();
    expect(el.querySelectorAll(".cn-molgrid-spinner")).toHaveLength(1);
    model.emit("images", { ...model.get("images"), 1: "<svg id='img1'></svg>" });
    expect(el.querySelector("#img1")).not.toBeNull();
  });

  it("never interprets user text as HTML", () => {
    const { el } = mount();
    const title = el.querySelector(".cn-molgrid-title");
    expect(title.textContent).toBe("<img src=x onerror=alert(1)>");
    expect(el.querySelector("img[src='x']")).toBeNull();
  });

  it("pages, sorts, filters and clusters", () => {
    const { model, el } = mount();
    el.querySelector(".cn-molgrid-next").click();
    expect([...el.querySelectorAll(".cn-molgrid-card")].map((c) => c.dataset.index)).toEqual(["2", "3"]);
    const sort = el.querySelector(".cn-molgrid-sort");
    sort.value = "MW"; sort.dispatchEvent(new Event("change", { bubbles: true }));
    expect(el.querySelector(".cn-molgrid-card").dataset.index).toBe("4");
    const search = el.querySelector(".cn-molgrid-search");
    search.value = "name1"; search.dispatchEvent(new Event("input", { bubbles: true }));
    expect(el.querySelectorAll(".cn-molgrid-card")).toHaveLength(1);
    search.value = ""; search.dispatchEvent(new Event("input", { bubbles: true }));
    el.querySelector(".cn-molgrid-cluster-item[data-cluster='odd']").click();
    expect([...el.querySelectorAll(".cn-molgrid-card")].map((c) => c.dataset.index)).toEqual(["3", "1"]);
    expect(model.get("visible")).toEqual([3, 1]);
  });

  it("selection actions publish sorted selections", () => {
    const { model, el } = mount();
    el.querySelector(".cn-molgrid-card[data-index='1'] .cn-molgrid-check").click();
    expect(model.get("selection")).toEqual([1]);
    el.querySelector(".cn-molgrid-action[data-action='select-all']").click();
    expect(model.get("selection")).toEqual([0, 1, 2, 3, 4]);
    el.querySelector(".cn-molgrid-action[data-action='invert']").click();
    expect(model.get("selection")).toEqual([]);
  });

  it("repeated SMARTS query re-requests", () => {
    const { model, el } = mount();
    el.querySelector(".cn-molgrid-mode").click();
    const search = el.querySelector(".cn-molgrid-search");
    search.value = "c1ccccc1"; search.dispatchEvent(new Event("input", { bubbles: true }));
    expect(model.get("smarts_request").seq).toBe(1);
    model.emit("smarts_result", { seq: 1, matches: [2], error: null });
    expect([...el.querySelectorAll(".cn-molgrid-card")].map((c) => c.dataset.index)).toEqual(["2"]);
    search.value = ""; search.dispatchEvent(new Event("input", { bubbles: true }));
    search.value = "c1ccccc1"; search.dispatchEvent(new Event("input", { bubbles: true }));
    expect(model.get("smarts_request").seq).toBe(2);
    model.emit("smarts_result", { seq: 2, matches: [], error: "Invalid SMARTS pattern: c1ccccc1" });
    expect(el.querySelector(".cn-molgrid-message").textContent).toContain("Invalid SMARTS");
  });

  it("drops images and republishes visible on revision change", () => {
    const { model, el } = mount();
    model.emit("images", {});
    model.emit("revision", 1);
    expect(el.querySelectorAll(".cn-molgrid-spinner")).toHaveLength(2);
    expect(model.get("visible")).toEqual([0, 1, 2, 3]);
  });

  it("static mode disables SMARTS and boots without errors for non-clustered grids", () => {
    const { el } = mount({ static: true, cluster_labels: null });
    expect(el.querySelector(".cn-molgrid-mode").disabled).toBe(true);
    expect(el.querySelector(".cn-molgrid-cluster")).toBeNull();
  });

  it("applies the configured theme to the grid root", () => {
    expect(mount({ theme: "dark" }).el.querySelector(".cn-molgrid").dataset.theme).toBe("dark");
    expect(mount({ theme: "light" }).el.querySelector(".cn-molgrid").dataset.theme).toBe("light");
  });
});

describe("hostile data", () => {
  beforeEach(() => { document.body.innerHTML = ""; });

  // One string carrying everything that ends an element, an attribute or the embedding script.
  const HOSTILE = "</script><img src=x onerror=alert(1)> \"quoted\" 'single' & <b>";
  const hostileItems = [{
    i: 0, title: HOSTILE, smiles: HOSTILE,
    fields: { MW: HOSTILE, Name: HOSTILE }, badges: [HOSTILE], cluster: HOSTILE,
  }];

  /** @returns {string[]} every attribute name present anywhere under the mount point */
  function attributeNames(root) {
    return [...root.querySelectorAll("*")].flatMap((node) => node.getAttributeNames());
  }

  /**
   * Mount the hostile grid with no images at all, so that every element under it came from
   * the module's own DOM building and nothing was contributed by the trusted image channel.
   */
  function mountHostile() {
    const model = new FakeModel({
      items: hostileItems,
      config: { ...config, cluster_labels: [HOSTILE], cluster_counts: true },
      images: {},
    });
    const el = document.createElement("div");
    document.body.appendChild(el);
    createGrid(model, el);
    return { model, el };
  }

  it("renders a hostile title, field, badge and cluster label as text only", () => {
    const { el } = mountHostile();

    // Nothing the payload spelled became an element, and no handler attribute exists.
    expect(el.querySelectorAll("img, script, iframe, svg, b")).toHaveLength(0);
    expect(el.querySelector("[src]")).toBeNull();
    expect(attributeNames(el).filter((name) => name.toLowerCase().startsWith("on"))).toEqual([]);

    // Each user string is one text node with the payload as its exact value; serialising that
    // node escapes the markup, which is what proves it was never parsed as markup.
    const title = el.querySelector(".cn-molgrid-title");
    expect(title.childNodes).toHaveLength(1);
    expect(title.childNodes[0].nodeType).toBe(3);
    expect(title.textContent).toBe(HOSTILE);
    expect(title.innerHTML).toContain("&lt;img src=x onerror=alert(1)&gt;");
    expect(el.querySelector(".cn-molgrid-badge").textContent).toBe(HOSTILE);
    expect([...el.querySelectorAll(".cn-molgrid-tooltip-row")].map((r) => r.textContent))
      .toContain(`MW: ${HOSTILE}`);

    // The cluster chip keeps the label in a data attribute, set as a plain value.
    const chip = el.querySelector(".cn-molgrid-cluster-item");
    expect(chip.getAttribute("data-cluster")).toBe(HOSTILE);
    expect(chip.textContent).toBe(`${HOSTILE} (1)`);
    chip.click();
    expect(el.querySelectorAll(".cn-molgrid-card")).toHaveLength(1);
  });

  it("keeps a hostile search query out of the DOM", () => {
    const { el } = mountHostile();
    const before = el.querySelectorAll("*").length;
    const search = el.querySelector(".cn-molgrid-search");
    search.value = HOSTILE;
    search.dispatchEvent(new Event("input", { bubbles: true }));
    expect(el.querySelectorAll("img, script, b")).toHaveLength(0);
    // The query filters; it is never written back into the page, so the card simply goes.
    expect(el.querySelectorAll(".cn-molgrid-card")).toHaveLength(1);
    expect(el.querySelectorAll("*").length).toBe(before);
  });

  it("inserts depiction markup as HTML, and only into an image cell", () => {
    // The images trait is the one trusted channel: it carries markup cnotebook rendered itself.
    const { model, el } = mount();
    expect(el.querySelector(".cn-molgrid-card[data-index='0'] .cn-molgrid-image svg#img0")).not.toBeNull();
    model.emit("images", { 0: "<svg id='img0'></svg>", 1: "<img id='img1' src='data:image/png;base64,AAA'>" });
    expect(el.querySelectorAll(".cn-molgrid-image > *")).toHaveLength(2);
    for (const node of el.querySelectorAll("img, svg")) {
      expect(node.closest(".cn-molgrid-image")).not.toBeNull();
    }
  });
});

describe("trait writes", () => {
  beforeEach(() => { document.body.innerHTML = ""; });

  it("publishes a new visible array on a page change and after a revision bump", () => {
    // traitlets and Backbone both drop an assignment equal to the current value, so every
    // publication has to be a container the model has not seen before.
    const { model, el } = mount();
    const first = model.get("visible");
    expect(first).toEqual([0, 1, 2, 3]);
    el.querySelector(".cn-molgrid-next").click();
    const second = model.get("visible");
    expect(second).toEqual([2, 3, 4]);
    expect(second).not.toBe(first);

    model.emit("images", { 2: "<svg id='img2'></svg>" });
    expect(el.querySelector("#img2")).not.toBeNull();
    model.emit("revision", 1);
    expect(el.querySelector("#img2")).toBeNull();
    expect(el.querySelectorAll(".cn-molgrid-spinner")).toHaveLength(2);
    const third = model.get("visible");
    expect(third).toEqual([2, 3, 4]);
    expect(third).not.toBe(second);
  });

  it("publishes a new selection array on every change and follows the kernel's selection", () => {
    const { model, el } = mount();
    const initial = model.get("selection");
    el.querySelector(".cn-molgrid-card[data-index='0'] .cn-molgrid-check").click();
    const afterCheck = model.get("selection");
    expect(afterCheck).toEqual([0]);
    expect(afterCheck).not.toBe(initial);
    el.querySelector(".cn-molgrid-card[data-index='1']").click();
    const afterCard = model.get("selection");
    expect(afterCard).toEqual([0, 1]);
    expect(afterCard).not.toBe(afterCheck);
    el.querySelector(".cn-molgrid-action[data-action='clear']").click();
    expect(model.get("selection")).toEqual([]);
    expect(model.get("selection")).not.toBe(afterCard);

    model.emit("selection", [4]);
    el.querySelector(".cn-molgrid-next").click();
    el.querySelector(".cn-molgrid-next").click();
    const card = el.querySelector(".cn-molgrid-card[data-index='4']");
    expect(card.classList.contains("cn-molgrid-selected")).toBe(true);
    expect(card.querySelector(".cn-molgrid-check").checked).toBe(true);
  });

  it("gives every SMARTS request a fresh object with a strictly increasing sequence", () => {
    const { model, el } = mount();
    el.querySelector(".cn-molgrid-mode").click();
    const search = el.querySelector(".cn-molgrid-search");
    const requests = [];
    for (let n = 0; n < 3; n += 1) {
      // The identical query three times over: only the sequence distinguishes the requests,
      // and without it the second one would never reach the kernel.
      search.value = "c1ccccc1";
      search.dispatchEvent(new Event("input", { bubbles: true }));
      requests.push(model.get("smarts_request"));
    }
    expect(requests.map((r) => r.seq)).toEqual([1, 2, 3]);
    expect(requests.map((r) => r.query)).toEqual(["c1ccccc1", "c1ccccc1", "c1ccccc1"]);
    expect(new Set(requests).size).toBe(3);

    // An answer to an abandoned sequence is ignored rather than shown.
    model.emit("smarts_result", { seq: 1, matches: [0], error: null });
    expect(el.querySelectorAll(".cn-molgrid-card")).toHaveLength(2);
    model.emit("smarts_result", { seq: 3, matches: [0], error: null });
    expect([...el.querySelectorAll(".cn-molgrid-card")].map((c) => c.dataset.index)).toEqual(["0"]);
  });

  it("shows a Python-side error and never publishes from a static grid", () => {
    const { model, el } = mount({ static: true });
    expect(model.get("visible")).toEqual([]);
    model.emit("error", "Depiction failed for 2 molecules");
    expect(el.querySelector(".cn-molgrid-message").textContent).toBe("Depiction failed for 2 molecules");
  });
});

describe("teardown", () => {
  beforeEach(() => { document.body.innerHTML = ""; });

  function mountView(model) {
    const el = document.createElement("div");
    document.body.appendChild(el);
    return { el, cleanup: widgetModule.render({ model, el }) };
  }

  it("detaches every subscription and removes the grid", () => {
    const { model, el, grid } = mount();
    expect(handlerCount(model)).toBeGreaterThan(0);
    grid.destroy();
    expect(handlerCount(model)).toBe(0);
    expect(el.querySelector(".cn-molgrid")).toBeNull();
    grid.destroy();
    expect(handlerCount(model)).toBe(0);
  });

  it("stops publishing visible once the view is gone", () => {
    const { model, grid } = mount();
    const lastVisible = model.get("visible");
    grid.destroy();
    model.emit("images", { 0: "<svg id='late'></svg>" });
    model.emit("revision", 7);
    // The kernel hears nothing more from a dead view, so it renders no images for it.
    expect(model.get("visible")).toBe(lastVisible);
    expect(document.querySelector("#late")).toBeNull();
  });

  it("goes inert even when the host model has no off", () => {
    // StaticModel and any hand-built host model lack Backbone's off; the handlers survive, so
    // the destroyed flag is what has to stop them.
    const model = new FakeModel({ items, config, images: {} });
    model.off = undefined;
    const el = document.createElement("div");
    document.body.appendChild(el);
    const grid = createGrid(model, el);
    const before = handlerCount(model);
    grid.destroy();
    expect(handlerCount(model)).toBe(before);
    const lastVisible = model.get("visible");
    model.emit("images", { 0: "<svg id='late'></svg>" });
    expect(model.get("visible")).toBe(lastVisible);
    expect(document.querySelector("#late")).toBeNull();
  });

  it("leaves one live subscriber set after four renders with cleanup", () => {
    // The model outlives the view: without the cleanup each re-run of the cell stacked another
    // permanent set of handlers on it.
    const model = new FakeModel({ items, config, images: {} });
    const first = mountView(model);
    const perView = handlerCount(model);
    expect(perView).toBeGreaterThan(0);
    let live = first;
    for (let n = 0; n < 3; n += 1) {
      live.cleanup();
      live = mountView(model);
      expect(handlerCount(model)).toBe(perView);
      expect(document.querySelectorAll(".cn-molgrid")).toHaveLength(1);
    }
    live.cleanup();
    expect(handlerCount(model)).toBe(0);
    expect(document.querySelectorAll(".cn-molgrid")).toHaveLength(0);
  });
});

describe("abandoned SMARTS queries", () => {
  beforeEach(() => { document.body.innerHTML = ""; });

  function askSmarts(el) {
    const search = el.querySelector(".cn-molgrid-search");
    search.value = "c1ccccc1";
    search.dispatchEvent(new Event("input", { bubbles: true }));
    return search;
  }

  it("ignores the answer to a query the user cleared", () => {
    const { model, el } = mount();
    el.querySelector(".cn-molgrid-mode").click();
    const search = askSmarts(el);
    expect(model.get("smarts_request").seq).toBe(1);
    search.value = ""; search.dispatchEvent(new Event("input", { bubbles: true }));
    model.emit("smarts_result", { seq: 1, matches: [2], error: null });
    // An empty box shows everything; it must not sit on the matches of a deleted query.
    expect([...el.querySelectorAll(".cn-molgrid-card")].map((c) => c.dataset.index)).toEqual(["0", "1"]);
    // The next request still carries a sequence the kernel has never seen.
    search.value = "c1ccccc1"; search.dispatchEvent(new Event("input", { bubbles: true }));
    expect(model.get("smarts_request").seq).toBeGreaterThan(1);
    model.emit("smarts_result", { seq: model.get("smarts_request").seq, matches: [2], error: null });
    expect([...el.querySelectorAll(".cn-molgrid-card")].map((c) => c.dataset.index)).toEqual(["2"]);
  });

  it("ignores the answer to a query abandoned by leaving SMARTS mode", () => {
    const { model, el } = mount();
    const mode = el.querySelector(".cn-molgrid-mode");
    mode.click();
    askSmarts(el);
    mode.click();
    expect(mode.textContent).toBe("Properties");
    model.emit("smarts_result", { seq: 1, matches: [], error: "Invalid SMARTS pattern: c1ccccc1" });
    // The error belongs to a question the Properties view is no longer asking.
    expect(el.querySelector(".cn-molgrid-message").textContent).toBe("");
  });

  it("redraws at once when a query already in the box enters SMARTS mode", () => {
    const { model, el } = mount();
    const search = el.querySelector(".cn-molgrid-search");
    search.value = "name1"; search.dispatchEvent(new Event("input", { bubbles: true }));
    expect(el.querySelectorAll(".cn-molgrid-card")).toHaveLength(1);
    model.emit("error", "Depiction failed for 1 molecule");
    expect(el.querySelector(".cn-molgrid-message").textContent).toBe("Depiction failed for 1 molecule");

    el.querySelector(".cn-molgrid-mode").click();
    // The request went out, and the view already shows the SMARTS state rather than waiting
    // for the answer to arrive before clearing the old message.
    expect(model.get("smarts_request")).toEqual({ seq: 1, query: "name1" });
    expect(el.querySelector(".cn-molgrid-message").textContent).toBe("");
    expect(el.querySelectorAll(".cn-molgrid-card")).toHaveLength(2);
  });
});

describe("config updates", () => {
  beforeEach(() => { document.body.innerHTML = ""; });

  it("re-applies image size, page size, theme and cluster chips", () => {
    const { model, el } = mount();
    const root = el.querySelector(".cn-molgrid");
    expect(root.style.getPropertyValue("--cn-molgrid-image-width")).toBe("100px");
    expect(root.style.getPropertyValue("--cn-molgrid-image-height")).toBe("80px");
    expect(el.querySelectorAll(".cn-molgrid-card")).toHaveLength(2);

    // set_render_options in Python republishes the whole config.
    model.emit("config", { ...config, image_width: 300, image_height: 240, page_size: 4, theme: "dark" });
    expect(root.style.getPropertyValue("--cn-molgrid-image-width")).toBe("300px");
    expect(root.style.getPropertyValue("--cn-molgrid-image-height")).toBe("240px");
    expect(el.querySelectorAll(".cn-molgrid-card")).toHaveLength(4);
    expect(root.dataset.theme).toBe("dark");
    expect(model.get("visible")).toEqual([0, 1, 2, 3, 4]);
    expect([...el.querySelectorAll(".cn-molgrid-sort option")].map((o) => o.value)).toEqual(["", "MW", "Name"]);

    model.emit("config", { ...config, cluster_labels: null });
    expect(el.querySelector(".cn-molgrid-cluster")).toBeNull();
    model.emit("config", { ...config, cluster_labels: ["even", "odd"] });
    expect([...el.querySelectorAll(".cn-molgrid-cluster-item")].map((c) => c.dataset.cluster)).toEqual(["even", "odd"]);
    expect(el.querySelectorAll(".cn-molgrid-card")).toHaveLength(2);
  });

  it("keeps the user's sort and selection across a config update", () => {
    const { model, el } = mount();
    const sort = el.querySelector(".cn-molgrid-sort");
    sort.value = "MW"; sort.dispatchEvent(new Event("change", { bubbles: true }));
    el.querySelector(".cn-molgrid-card[data-index='4'] .cn-molgrid-check").click();
    model.emit("config", { ...config, image_width: 120 });
    expect(el.querySelector(".cn-molgrid-sort").value).toBe("MW");
    expect(el.querySelector(".cn-molgrid-card").dataset.index).toBe("4");
    expect(model.get("selection")).toEqual([4]);
  });
});

describe("CSV export", () => {
  beforeEach(() => { document.body.innerHTML = ""; });

  it("neutralises formula-leading cells and quotes separators and carriage returns", () => {
    // A title or SD field is the molecule author's text, and a spreadsheet runs a cell that
    // opens with =, +, -, @, a tab or a carriage return when the export is opened.
    const risky = [
      { i: 0, title: "t0", smiles: "=cmd|'/c calc'!A1", fields: { MW: "-1+2", Name: "@SUM(A1)" }, badges: [], cluster: "even" },
      { i: 1, title: "t1", smiles: "C", fields: { MW: "a\rb", Name: "+1" }, badges: [], cluster: "odd" },
      { i: 2, title: "t2", smiles: "C", fields: { MW: "\tlead", Name: 'plain, "quoted"' }, badges: [], cluster: "even" },
    ];
    const model = new FakeModel({ items: risky, config: { ...config, page_size: 10 }, images: {} });
    const el = document.createElement("div");
    document.body.appendChild(el);
    createGrid(model, el);

    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue(undefined);
    try {
      el.querySelector(".cn-molgrid-action[data-action='copy-csv']").click();
      expect(writeText).toHaveBeenCalledTimes(1);
      expect(writeText.mock.calls[0][0].split("\n")).toEqual([
        "smiles,MW,Name",
        "'=cmd|'/c calc'!A1,'-1+2,'@SUM(A1)",
        'C,"a\rb",\'+1',
        "C,'\tlead,\"plain, \"\"quoted\"\"\"",
      ]);
    } finally {
      writeText.mockRestore();
    }
  });
});

describe("the static document", () => {
  beforeEach(() => { document.body.innerHTML = ""; });

  it("drives a grid from StaticModel with no kernel to answer it", () => {
    const el = document.createElement("div");
    document.body.appendChild(el);
    const model = new StaticModel({ items, config: { ...config, static: true }, images: { 0: "<svg id='img0'></svg>" }, selection: [], revision: 0 });
    createGrid(model, el);
    expect(el.querySelectorAll(".cn-molgrid-card")).toHaveLength(2);
    expect(el.querySelector("#img0")).not.toBeNull();
    // Nothing is asked for: the document already holds every image.
    expect(model.get("visible")).toBeUndefined();
  });

  it("self-mounts over the embedded payload when the document sets the global", async () => {
    document.body.innerHTML = '<div id="molgrid-root"></div>';
    globalThis.window.__CNOTEBOOK_MOLGRID_STATIC__ = {
      items,
      config: { ...config, static: true, cluster_labels: null },
      images: { 0: "<svg id='static0'></svg>", 1: "<svg id='static1'></svg>" },
    };
    try {
      // The boot block runs at module evaluation, so the module has to be evaluated again
      // with the global in place.
      vi.resetModules();
      await import("../../cnotebook/grid/static/molgrid.js");
    } finally {
      delete globalThis.window.__CNOTEBOOK_MOLGRID_STATIC__;
    }
    const root = document.getElementById("molgrid-root");
    expect(root.querySelectorAll(".cn-molgrid-card")).toHaveLength(2);
    expect(root.querySelector("#static0")).not.toBeNull();
    expect(root.querySelector("#static1")).not.toBeNull();
    expect(root.querySelector(".cn-molgrid-mode").disabled).toBe(true);
  });

  it("does not self-mount when the global is absent", async () => {
    vi.resetModules();
    await import("../../cnotebook/grid/static/molgrid.js");
    expect(document.querySelector(".cn-molgrid")).toBeNull();
  });
});

describe("the embedded module source", () => {
  it("is pure printable ASCII and cannot close the script element it is embedded in", () => {
    // Task 32 embeds this module in a script element of the static document and the stylesheet
    // in a style element. A non-ASCII byte would make the finished document impossible to
    // encode, and either closing sequence would end its element early and spill the rest of
    // the file into the page as markup.
    const source = readFileSync(MODULE_PATH, "utf8");
    const style = readFileSync(STYLE_PATH, "utf8");
    expect(source).toMatch(/^[\t\n\x20-\x7e]*$/);
    expect(style).toMatch(/^[\t\n\x20-\x7e]*$/);
    expect(source).not.toContain(`<${"/script"}`);
    expect(style).not.toContain(`<${"/style"}`);
  });
});
