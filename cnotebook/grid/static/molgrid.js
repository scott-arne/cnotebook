// MolGrid front end: renders into the output cell (anywidget) or self-mounts in the static
// document. The file is pure printable ASCII and never spells the sequence that closes a
// script element, because cnotebook's static document embeds the whole module inside one.
//
// Trust boundary. Everything derived from the user's molecules - titles, field values, badges,
// cluster labels, SMILES, the export text and the search box - reaches the DOM only through
// textContent, createTextNode or setAttribute with a plain value, so hostile data can never
// open an element or an attribute. The single exception is the depiction markup carried by the
// `images` trait: that HTML is produced by cnotebook's own renderer, is trusted for that
// reason, and is inserted as HTML into a card's image slot and nowhere else.

const PROP_MODE = "properties";
const SMARTS_MODE = "smarts";

/**
 * Resolve the effective colour scheme for the grid root.
 *
 * An explicit "light" or "dark" wins. "auto" reads JupyterLab's `--jp-layout-color1` from the
 * host document and classifies it by luminance, which is what makes the grid follow a lab
 * theme; outside JupyterLab there is no such variable and the media query decides.
 *
 * @param {string} theme - "light", "dark" or "auto"
 * @param {HTMLElement} el - mount point, used to reach the host document
 * @returns {"light"|"dark"}
 */
export function resolveTheme(theme, el) {
  if (theme === "light" || theme === "dark") return theme;
  const jp = getComputedStyle(el.ownerDocument.documentElement).getPropertyValue("--jp-layout-color1").trim();
  const match = /^#?([0-9a-f]{6})$/i.exec(jp);
  if (match) {
    const value = parseInt(match[1], 16);
    const luminance = 0.299 * ((value >> 16) & 255) + 0.587 * ((value >> 8) & 255) + 0.114 * (value & 255);
    return luminance < 128 ? "dark" : "light";
  }
  return typeof matchMedia === "function" && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/**
 * Parse a field value as a number.
 *
 * @param {unknown} value
 * @returns {number|null} the number, or null when the value is blank or not numeric
 */
function numeric(value) {
  const n = Number(value);
  return value !== "" && value !== null && value !== undefined && !Number.isNaN(n) ? n : null;
}

/**
 * Filter items by text query, selected clusters and SMARTS matches.
 *
 * @param {Array<object>} items - the full item index
 * @param {{query: string, mode: string, clusters: Set<string>, smartsMatches: Set<number>|null,
 *   searchFields?: string[]}} state - current filter state
 * @returns {Array<object>} the matching items, in input order
 */
export function applyFilters(items, { query, mode, clusters, smartsMatches, searchFields = ["Name"] }) {
  const q = (query || "").trim().toLowerCase();
  return items.filter((item) => {
    if (clusters && clusters.size && !clusters.has(item.cluster)) return false;
    // A SMARTS search has no matches until the kernel answers; showing everything until then
    // beats blanking the grid on every keystroke.
    if (mode === SMARTS_MODE) return smartsMatches ? smartsMatches.has(item.i) : true;
    if (!q) return true;
    const haystack = [item.title || "", ...searchFields.map((f) => (item.fields || {})[f] || "")];
    return haystack.some((text) => String(text).toLowerCase().includes(q));
  });
}

/**
 * Sort items by a field, numerically when every value parses as a number.
 *
 * @param {Array<object>} items
 * @param {{field: string, descending: boolean}|null} sortBy
 * @returns {Array<object>} a new array; the input is never reordered
 */
export function sortItems(items, sortBy) {
  if (!sortBy || !sortBy.field) return items.slice();
  const values = items.map((item) => (item.fields || {})[sortBy.field]);
  const allNumeric = values.every((v) => numeric(v) !== null);
  const sorted = items.slice().sort((a, b) => {
    const va = (a.fields || {})[sortBy.field];
    const vb = (b.fields || {})[sortBy.field];
    const cmp = allNumeric ? numeric(va) - numeric(vb) : String(va ?? "").localeCompare(String(vb ?? ""));
    return sortBy.descending ? -cmp : cmp;
  });
  return sorted;
}

/**
 * Model adapter for the static document, where there is no kernel to talk to.
 *
 * It answers `get` from the embedded payload and swallows writes, so the controller needs no
 * separate code path: a static grid simply never hears back from anything it publishes.
 */
export class StaticModel {
  /** @param {object} state - the embedded payload: items, config, images, selection, revision */
  constructor(state) { this.state = state; this.handlers = {}; }
  /** @param {string} name @returns {unknown} */
  get(name) { return this.state[name]; }
  /** @param {string} name @param {unknown} value */
  set(name, value) { this.state[name] = value; }
  /** No kernel to sync with. */
  save_changes() {}
  /** @param {string} event @param {Function} handler */
  on(event, handler) { (this.handlers[event] ||= []).push(handler); }
}

/**
 * Create an element, giving it its text as text.
 *
 * Every caller passes user-derived strings through the `text` argument, which is why this
 * helper assigns textContent and there is no markup-taking variant of it.
 *
 * @param {string} tag
 * @param {string} [className]
 * @param {string} [text]
 * @returns {HTMLElement}
 */
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/**
 * Build one option of the sort menu.
 *
 * The label carries a column name, which is user data, so it is set as text. The Option
 * constructor is not used: it is absent from some DOM implementations, including the test
 * environment.
 *
 * @param {string} label
 * @param {string} value
 * @returns {HTMLOptionElement}
 */
function sortOption(label, value) {
  const option = element("option", null, label);
  option.value = value;
  return option;
}

/**
 * Quote a CSV field when it carries a separator, a quote or a newline.
 *
 * @param {unknown} value
 * @returns {string}
 */
function csvEscape(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/**
 * Save text to a file through a transient object URL.
 *
 * @param {string} content
 * @param {string} filename
 * @param {string} type - MIME type
 */
function download(content, filename, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}

/**
 * Create the grid controller: build the DOM, wire the events, subscribe to the model.
 *
 * @param {object} model - anywidget model or StaticModel
 * @param {HTMLElement} el - mount point
 * @returns {{render: () => void, state: object, root: HTMLElement}}
 */
export function createGrid(model, el) {
  const config = model.get("config") || {};
  const items = model.get("items") || [];
  const state = {
    query: "", mode: PROP_MODE, clusters: new Set(), smartsMatches: null, page: 0,
    sortBy: config.sort_by || null, selection: new Set(model.get("selection") || []),
    images: { ...(model.get("images") || {}) }, revision: model.get("revision") || 0, smartsSeq: 0, message: "",
  };
  const pageSize = Math.max(1, config.page_size || 24);

  const root = element("div", "cn-molgrid");
  root.dataset.theme = resolveTheme(config.theme, el);
  root.style.setProperty("--cn-molgrid-image-width", `${config.image_width || 260}px`);
  root.style.setProperty("--cn-molgrid-image-height", `${config.image_height || 240}px`);
  el.appendChild(root);

  // toolbar --------------------------------------------------------------
  const toolbar = element("div", "cn-molgrid-toolbar");
  const search = element("input", "cn-molgrid-search");
  search.type = "search"; search.placeholder = "Search...";
  const modeButton = element("button", "cn-molgrid-mode", "Properties");
  modeButton.type = "button";
  if (config.static) { modeButton.disabled = true; modeButton.title = "SMARTS search needs a live kernel"; }
  const sortSelect = element("select", "cn-molgrid-sort");
  sortSelect.appendChild(sortOption("Sort: none", ""));
  const sortable = Array.from(new Set(Object.keys((items[0] || {}).fields || {})));
  for (const field of sortable) sortSelect.appendChild(sortOption(`Sort: ${field}`, field));
  if (state.sortBy) sortSelect.value = state.sortBy.field;
  const sortDir = element("button", "cn-molgrid-sort-dir", state.sortBy && state.sortBy.descending ? "desc" : "asc");
  sortDir.type = "button";
  const info = element("span", "cn-molgrid-info");
  const actions = element("div", "cn-molgrid-actions");
  for (const [action, label] of [["select-all", "Select all"], ["clear", "Clear selection"], ["invert", "Invert selection"], ["copy-csv", "Copy CSV"], ["save-smiles", "Save SMILES"], ["save-csv", "Save CSV"]]) {
    const button = element("button", "cn-molgrid-action", label);
    button.type = "button"; button.dataset.action = action; actions.appendChild(button);
  }
  toolbar.append(search, modeButton, sortSelect, sortDir, info, actions);
  root.appendChild(toolbar);

  let clusterBox = null;
  if (config.cluster_labels && config.cluster_labels.length) {
    clusterBox = element("div", "cn-molgrid-cluster");
    const counts = new Map();
    for (const item of items) counts.set(item.cluster, (counts.get(item.cluster) || 0) + 1);
    for (const label of config.cluster_labels) {
      const chip = element("button", "cn-molgrid-cluster-item", config.cluster_counts ? `${label} (${counts.get(label) || 0})` : label);
      chip.type = "button"; chip.dataset.cluster = label; clusterBox.appendChild(chip);
    }
    root.appendChild(clusterBox);
  }

  const message = element("div", "cn-molgrid-message");
  const list = element("div", "cn-molgrid-list");
  const pager = element("div", "cn-molgrid-pager");
  const prev = element("button", "cn-molgrid-prev", "Previous");
  const next = element("button", "cn-molgrid-next", "Next");
  prev.type = "button"; next.type = "button";
  const pageInfo = element("span", "cn-molgrid-page");
  pager.append(prev, pageInfo, next);
  root.append(message, list, pager);

  // state helpers -----------------------------------------------------------

  /**
   * Write a trait and sync it.
   *
   * Every value handed in is a freshly built array or object. traitlets and Backbone both drop
   * an assignment equal to the current value, so mutating a published container in place would
   * lose the update outright; requests that can legitimately repeat carry a sequence number.
   *
   * @param {string} name
   * @param {unknown} value
   */
  function publish(name, value) { model.set(name, value); model.save_changes(); }

  /** @returns {Array<object>} the items that pass the filters, in sort order */
  function matching() {
    return sortItems(applyFilters(items, { ...state, searchFields: config.search_fields || [] }), state.sortBy);
  }

  /** @param {Array<object>} list @returns {Array<object>} the slice shown on the current page */
  function currentPage(list) { return list.slice(state.page * pageSize, (state.page + 1) * pageSize); }

  /**
   * Build one card.
   *
   * @param {object} item - one entry of the item index
   * @returns {HTMLElement}
   */
  function renderCard(item) {
    const card = element("div", "cn-molgrid-card");
    card.dataset.index = String(item.i);
    if (state.selection.has(item.i)) card.classList.add("cn-molgrid-selected");
    if (config.select) {
      const check = element("input", "cn-molgrid-check");
      check.type = "checkbox"; check.checked = state.selection.has(item.i);
      check.addEventListener("click", (event) => { event.stopPropagation(); toggle(item.i); });
      card.appendChild(check);
    }
    if (config.information) {
      const infoButton = element("button", "cn-molgrid-infobtn", "i");
      infoButton.type = "button";
      const tooltip = element("div", "cn-molgrid-tooltip");
      tooltip.appendChild(element("div", "cn-molgrid-tooltip-row", `Index: ${item.i}`));
      if (item.title) tooltip.appendChild(element("div", "cn-molgrid-tooltip-row", `Title: ${item.title}`));
      for (const field of config.info_fields || []) {
        const value = (item.fields || {})[field];
        if (value) tooltip.appendChild(element("div", "cn-molgrid-tooltip-row", `${field}: ${value}`));
      }
      infoButton.addEventListener("click", (event) => { event.stopPropagation(); tooltip.classList.toggle("cn-molgrid-pinned"); });
      card.append(infoButton, tooltip);
    }
    const slot = element("div", "cn-molgrid-image");
    const image = state.images[String(item.i)];
    // The one trusted HTML channel in this module: `images` holds depiction markup rendered by
    // cnotebook itself, never anything the user's data could have shaped. It goes here, into
    // the image slot, and into no other node.
    if (image) slot.innerHTML = image; else slot.appendChild(element("div", "cn-molgrid-spinner"));
    card.appendChild(slot);
    if (config.title && item.title) card.appendChild(element("div", "cn-molgrid-title", item.title));
    if (item.badges && item.badges.length) {
      const badges = element("div", "cn-molgrid-badges");
      for (const badge of item.badges) badges.appendChild(element("span", "cn-molgrid-badge", badge));
      card.appendChild(badges);
    }
    card.addEventListener("click", () => { if (config.select) toggle(item.i); });
    return card;
  }

  /** Redraw the current page and republish the indices whose images are wanted. */
  function render() {
    const all = matching();
    const pages = Math.max(1, Math.ceil(all.length / pageSize));
    state.page = Math.min(state.page, pages - 1);
    const page = currentPage(all);
    list.replaceChildren(...page.map(renderCard));
    info.textContent = `Showing ${all.length ? state.page * pageSize + 1 : 0}-${Math.min((state.page + 1) * pageSize, all.length)} of ${all.length} molecules`;
    pageInfo.textContent = `Page ${state.page + 1} of ${pages}`;
    prev.disabled = state.page === 0; next.disabled = state.page >= pages - 1;
    message.textContent = state.message;
    const nextPage = all.slice((state.page + 1) * pageSize, (state.page + 2) * pageSize);
    const visible = [...page, ...nextPage].map((item) => item.i);
    // The next page is requested with the current one so that paging forward shows depictions
    // rather than spinners. A static grid already holds every image and has nobody to ask.
    if (!config.static) publish("visible", visible);
  }

  /** @param {number} index - toggle one molecule's selection and publish the result */
  function toggle(index) {
    if (state.selection.has(index)) state.selection.delete(index); else state.selection.add(index);
    publish("selection", [...state.selection].sort((a, b) => a - b));
    render();
  }

  /** @returns {Array<object>} the rows an export covers: the selection, or everything matching */
  function exportRows() {
    const chosen = state.selection.size ? matching().filter((item) => state.selection.has(item.i)) : matching();
    return chosen;
  }

  /** @param {Array<object>} rows @returns {string} CSV text of SMILES plus the export columns */
  function toCsv(rows) {
    const columns = ["smiles", ...(config.export_columns || [])];
    return [columns.map(csvEscape).join(","), ...rows.map((r) => columns.map((c) => csvEscape(c === "smiles" ? r.smiles : (r.fields || {})[c])).join(","))].join("\n");
  }

  // events --------------------------------------------------------------------
  search.addEventListener("input", () => {
    state.query = search.value; state.page = 0;
    if (state.mode === SMARTS_MODE) {
      if (!state.query.trim()) { state.smartsMatches = null; state.message = ""; render(); return; }
      // The sequence, not the query text, is what makes the request new: re-running the same
      // pattern has to reach the kernel, and an answer to an abandoned query has to be
      // recognisable as stale when it arrives.
      state.smartsSeq += 1;
      publish("smarts_request", { seq: state.smartsSeq, query: state.query.trim() });
      return;
    }
    render();
  });
  modeButton.addEventListener("click", () => {
    state.mode = state.mode === PROP_MODE ? SMARTS_MODE : PROP_MODE;
    modeButton.textContent = state.mode === PROP_MODE ? "Properties" : "SMARTS";
    state.smartsMatches = null; state.message = ""; state.page = 0;
    search.dispatchEvent(new Event("input"));
  });
  sortSelect.addEventListener("change", () => {
    state.sortBy = sortSelect.value ? { field: sortSelect.value, descending: sortDir.textContent === "desc" } : null;
    state.page = 0; render();
  });
  sortDir.addEventListener("click", () => {
    sortDir.textContent = sortDir.textContent === "asc" ? "desc" : "asc";
    if (state.sortBy) { state.sortBy = { ...state.sortBy, descending: sortDir.textContent === "desc" }; render(); }
  });
  prev.addEventListener("click", () => { state.page -= 1; render(); });
  next.addEventListener("click", () => { state.page += 1; render(); });
  if (clusterBox) {
    clusterBox.addEventListener("click", (event) => {
      const chip = event.target.closest(".cn-molgrid-cluster-item");
      if (!chip) return;
      const label = chip.dataset.cluster;
      if (state.clusters.has(label)) state.clusters.delete(label); else state.clusters.add(label);
      chip.classList.toggle("cn-molgrid-cluster-active", state.clusters.has(label));
      state.page = 0; render();
    });
  }
  actions.addEventListener("click", (event) => {
    const button = event.target.closest(".cn-molgrid-action");
    if (!button) return;
    const visibleIds = matching().map((item) => item.i);
    switch (button.dataset.action) {
      case "select-all": visibleIds.forEach((i) => state.selection.add(i)); break;
      case "clear": state.selection.clear(); break;
      case "invert": visibleIds.forEach((i) => (state.selection.has(i) ? state.selection.delete(i) : state.selection.add(i))); break;
      // A denied clipboard permission rejects the promise, and there is nothing useful to do
      // with it here; leaving it unhandled would log an unhandled rejection in the notebook.
      case "copy-csv": if (navigator.clipboard) Promise.resolve(navigator.clipboard.writeText(toCsv(exportRows()))).catch(() => {}); break;
      case "save-smiles": download(exportRows().map((r) => r.smiles).filter(Boolean).join("\n"), "molgrid.smi", "chemical/x-daylight-smiles"); break;
      case "save-csv": download(toCsv(exportRows()), "molgrid.csv", "text/csv"); break;
      default: break;
    }
    publish("selection", [...state.selection].sort((a, b) => a - b));
    render();
  });

  model.on("change:images", () => { state.images = { ...(model.get("images") || {}) }; render(); });
  // A new revision invalidates every depiction: the images this view holds are of the previous
  // render options. Dropping them puts spinners back, and the render that follows republishes
  // the visible window so the kernel knows what to send first.
  model.on("change:revision", () => { state.images = {}; state.revision = model.get("revision"); render(); });
  model.on("change:selection", () => { state.selection = new Set(model.get("selection") || []); render(); });
  model.on("change:smarts_result", () => {
    const result = model.get("smarts_result") || {};
    // An answer to a query the user has already replaced would show the wrong molecules.
    if (result.seq !== state.smartsSeq) return;
    state.smartsMatches = result.error ? new Set() : new Set(result.matches || []);
    state.message = result.error || "";
    state.page = 0; render();
  });
  model.on("change:error", () => { state.message = model.get("error") || ""; render(); });

  render();
  return { render, state, root };
}

export default {
  /**
   * anywidget entry point.
   *
   * @param {{model: object, el: HTMLElement}} view
   */
  render({ model, el }) {
    createGrid(model, el);
  },
};

// Static document boot. cnotebook's to_html() writes the payload into the page before this
// module runs, so its presence is what distinguishes a saved document from a live widget.
if (typeof window !== "undefined" && window.__CNOTEBOOK_MOLGRID_STATIC__) {
  const data = window.__CNOTEBOOK_MOLGRID_STATIC__;
  const mountPoint = document.getElementById("molgrid-root") || document.body;
  createGrid(new StaticModel({ items: data.items, config: data.config, images: data.images, selection: data.selection || [], revision: 0 }), mountPoint);
}
