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
// Shown while the kernel is matching, so a replaced query never leaves the previous answer on
// screen as if it were the answer to what is in the box now.
const SEARCHING = "Searching...";

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
 * Is a field value absent?
 *
 * @param {unknown} value
 * @returns {boolean}
 */
function blank(value) {
  return value === null || value === undefined || value === "";
}

/**
 * Sort items by a field, comparing numbers as numbers and sinking the gaps.
 *
 * The decision is made per pair rather than per column: a measured column almost always has
 * holes in it, and a single missing value used to demote the whole column to a string
 * comparison, which orders 10 before 2. Values that are missing, and values that are not
 * numbers in an otherwise numeric column, sort after everything else in both directions -
 * a reversal should not fill the first page with empty cards. Columns where nothing parses
 * are genuinely textual and keep the locale-aware string comparison.
 *
 * @param {Array<object>} items
 * @param {{field: string, descending: boolean}|null} sortBy
 * @returns {Array<object>} a new array; the input is never reordered
 */
export function sortItems(items, sortBy) {
  if (!sortBy || !sortBy.field) return items.slice();
  const direction = sortBy.descending ? -1 : 1;
  return items.slice().sort((a, b) => {
    const va = (a.fields || {})[sortBy.field];
    const vb = (b.fields || {})[sortBy.field];
    const na = numeric(va);
    const nb = numeric(vb);
    if (na !== null && nb !== null) return (na - nb) * direction;
    // Missing before non-numeric: a blank cell is last whatever the column holds, and a word
    // in a numeric column is last too, but two words are compared as words.
    if (blank(va) || blank(vb)) {
      if (blank(va) && blank(vb)) return 0;
      return blank(va) ? 1 : -1;
    }
    if (na !== null || nb !== null) return na !== null ? -1 : 1;
    return String(va).localeCompare(String(vb)) * direction;
  });
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

// Excel, LibreOffice and Google Sheets evaluate a cell that opens with one of these as a
// formula, and a leading tab or carriage return is stripped before that test is applied. A
// molecule title or SD field is the attacker's text, so an export opened on someone else's
// machine would run it.
const FORMULA_LEAD = /^[=+\-@\t\r]/;

/**
 * Render a value as a CSV field: defused if a spreadsheet would run it, quoted if it would
 * otherwise break the row.
 *
 * The leading single quote is the conventional neutraliser: spreadsheets keep the cell as text
 * and do not show the quote. A bare carriage return has to force quoting too, because a
 * consumer that splits on CR or CRLF would otherwise read one field as two rows.
 *
 * @param {unknown} value
 * @returns {string}
 */
function csvEscape(value) {
  const text = value === null || value === undefined ? "" : String(value);
  const safe = FORMULA_LEAD.test(text) ? `'${text}` : text;
  return /[",\n\r]/.test(safe) ? `"${safe.replace(/"/g, '""')}"` : safe;
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
 * Mint the token that identifies one view in a SMARTS exchange.
 *
 * One widget can be displayed in several cells at once, and every view shares the model, so a
 * sequence number alone cannot say whose answer an incoming `smarts_result` is: two views that
 * both started counting at zero would both claim the other's matches. The token is random per
 * controller, so it separates them, and the kernel only has to echo it back.
 *
 * @returns {string}
 */
function viewToken() {
  const source = typeof crypto !== "undefined" ? crypto : null;
  if (source && typeof source.randomUUID === "function") return source.randomUUID();
  return `v-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;
}

/**
 * Read a sequence number out of a trait value.
 *
 * @param {unknown} carrier - a `smarts_request` or `smarts_result` value, possibly absent
 * @returns {number} the sequence it carries, or 0
 */
function seqOf(carrier) {
  const seq = Number((carrier || {}).seq);
  return Number.isFinite(seq) && seq > 0 ? seq : 0;
}

/**
 * Create the grid controller: build the DOM, wire the events, subscribe to the model.
 *
 * @param {object} model - anywidget model or StaticModel
 * @param {HTMLElement} el - mount point
 * @returns {{render: () => void, destroy: () => void, state: object, root: HTMLElement}}
 */
export function createGrid(model, el) {
  let config = model.get("config") || {};
  const items = model.get("items") || [];
  const state = {
    query: "", mode: PROP_MODE, clusters: new Set(), smartsMatches: null, page: 0,
    sortBy: config.sort_by || null, selection: new Set(model.get("selection") || []),
    images: { ...(model.get("images") || {}) }, revision: model.get("revision") || 0,
    // A rebuilt view inherits the exchange already recorded on the model: restarting the count
    // would let a repeated query land on a value the trait already holds, which traitlets drops
    // as a non-change, so the kernel would never hear the question.
    smartsSeq: Math.max(seqOf(model.get("smarts_request")), seqOf(model.get("smarts_result"))),
    awaitingSmarts: false, message: "", view: viewToken(), pinned: new Set(),
  };
  let pageSize = Math.max(1, config.page_size || 24);
  const observers = [];
  let destroyed = false;

  const root = element("div", "cn-molgrid");
  el.appendChild(root);

  // toolbar --------------------------------------------------------------
  const toolbar = element("div", "cn-molgrid-toolbar");
  const search = element("input", "cn-molgrid-search");
  search.type = "search"; search.placeholder = "Search...";
  const modeButton = element("button", "cn-molgrid-mode", "Properties");
  modeButton.type = "button";
  const sortSelect = element("select", "cn-molgrid-sort");
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
   * A torn-down view publishes nothing: its `visible` would otherwise keep the kernel rendering
   * images for a grid that is no longer in the document.
   *
   * @param {string} name
   * @param {unknown} value
   */
  function publish(name, value) {
    if (destroyed) return;
    model.set(name, value);
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
    // The guard covers a host model with no `off`: its handlers survive teardown, so they have
    // to become inert rather than redraw a detached grid.
    const guarded = () => { if (!destroyed) handler(); };
    model.on(event, guarded);
    observers.push([event, guarded]);
  }

  /** Rebuild the sort menu, keeping whatever the user has chosen. */
  function buildSortOptions() {
    const chosen = state.sortBy ? state.sortBy.field : "";
    const fields = Array.from(new Set(Object.keys((items[0] || {}).fields || {})));
    sortSelect.replaceChildren(sortOption("Sort: none", ""), ...fields.map((f) => sortOption(`Sort: ${f}`, f)));
    sortSelect.value = chosen;
  }

  /** Rebuild the cluster chips, or remove the row entirely when there are no clusters. */
  function buildClusterChips() {
    const labels = config.cluster_labels || [];
    if (!labels.length) {
      // A grid with no clusters has no cluster row at all, not an empty one.
      if (clusterBox) { clusterBox.remove(); clusterBox = null; }
      state.clusters.clear();
      return;
    }
    if (!clusterBox) {
      clusterBox = element("div", "cn-molgrid-cluster");
      clusterBox.addEventListener("click", onClusterClick);
      root.insertBefore(clusterBox, message);
    }
    // A label that has gone would otherwise keep filtering from a chip nobody can see.
    for (const label of [...state.clusters]) if (!labels.includes(label)) state.clusters.delete(label);
    const counts = new Map();
    for (const item of items) counts.set(item.cluster, (counts.get(item.cluster) || 0) + 1);
    clusterBox.replaceChildren(...labels.map((label) => {
      const chip = element("button", "cn-molgrid-cluster-item", config.cluster_counts ? `${label} (${counts.get(label) || 0})` : label);
      chip.type = "button";
      chip.dataset.cluster = label;
      if (state.clusters.has(label)) chip.classList.add("cn-molgrid-cluster-active");
      return chip;
    }));
  }

  /**
   * Apply everything derived from `config` to the chrome that shows it.
   *
   * Python republishes `config` when render options change the image size, so none of these
   * values can be read once at construction and left alone.
   */
  function applyConfig() {
    root.dataset.theme = resolveTheme(config.theme, el);
    root.style.setProperty("--cn-molgrid-image-width", `${config.image_width || 260}px`);
    root.style.setProperty("--cn-molgrid-image-height", `${config.image_height || 240}px`);
    pageSize = Math.max(1, config.page_size || 24);
    modeButton.disabled = Boolean(config.static);
    modeButton.title = config.static ? "SMARTS search needs a live kernel" : "";
    buildSortOptions();
    buildClusterChips();
  }

  /**
   * Abandon the SMARTS request in flight, if there is one.
   *
   * Moving the sequence past an outstanding request is what invalidates it: the answer that
   * arrives afterwards no longer matches, so it cannot filter a cleared box down to the matches
   * of a deleted query or report its error from the Properties view. Nothing is published - the
   * kernel's answer is simply no longer wanted.
   */
  function abandonSmarts() {
    if (state.awaitingSmarts) { state.smartsSeq += 1; state.awaitingSmarts = false; }
    state.smartsMatches = null;
    state.message = "";
  }

  /**
   * Toggle one cluster chip.
   *
   * @param {MouseEvent} event
   */
  function onClusterClick(event) {
    const chip = event.target.closest(".cn-molgrid-cluster-item");
    if (!chip) return;
    const label = chip.dataset.cluster;
    if (state.clusters.has(label)) state.clusters.delete(label); else state.clusters.add(label);
    chip.classList.toggle("cn-molgrid-cluster-active", state.clusters.has(label));
    state.page = 0; render();
  }

  /** @returns {Array<object>} the items that pass the filters, in sort order */
  function matching() {
    return sortItems(applyFilters(items, { ...state, searchFields: config.search_fields || [] }), state.sortBy);
  }

  /** @param {Array<object>} list @returns {Array<object>} the slice shown on the current page */
  function currentPage(list) { return list.slice(state.page * pageSize, (state.page + 1) * pageSize); }

  /**
   * The fields the hover surface lists.
   *
   * `tooltip_fields` is the grid's own argument for this and wins whenever it names anything.
   * The information fields are the fallback, which is both what a grid that was never given
   * tooltip fields has always shown and what an older payload with no such key carries.
   *
   * @returns {string[]}
   */
  function tooltipFields() {
    const chosen = config.tooltip_fields;
    return chosen && chosen.length ? chosen : (config.info_fields || []);
  }

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
      // A pin is the user's, not the card's: the card is rebuilt by every image that arrives,
      // and reading the pinned set here is what keeps an open tooltip open through that.
      if (state.pinned.has(item.i)) tooltip.classList.add("cn-molgrid-pinned");
      tooltip.appendChild(element("div", "cn-molgrid-tooltip-row", `Index: ${item.i}`));
      if (item.title) tooltip.appendChild(element("div", "cn-molgrid-tooltip-row", `Title: ${item.title}`));
      for (const field of tooltipFields()) {
        const value = (item.fields || {})[field];
        if (value) tooltip.appendChild(element("div", "cn-molgrid-tooltip-row", `${field}: ${value}`));
      }
      infoButton.addEventListener("click", (event) => {
        event.stopPropagation();
        if (state.pinned.has(item.i)) state.pinned.delete(item.i); else state.pinned.add(item.i);
        tooltip.classList.toggle("cn-molgrid-pinned", state.pinned.has(item.i));
      });
      // Reading a pinned tooltip means clicking on it, and the card underneath treats a click
      // as a selection, so the two gestures have to be kept apart.
      tooltip.addEventListener("click", (event) => event.stopPropagation());
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
      if (state.query.trim()) {
        // The sequence, not the query text, is what makes the request new: re-running the same
        // pattern has to reach the kernel, and an answer to an abandoned query has to be
        // recognisable as stale when it arrives. The view token says which grid asked.
        state.smartsSeq += 1;
        state.awaitingSmarts = true;
        // The previous answer belongs to the previous query. Leaving its matches and its error
        // on screen would present them as the answer to the pattern now in the box.
        state.smartsMatches = null;
        state.message = SEARCHING;
        publish("smarts_request", { seq: state.smartsSeq, query: state.query.trim(), view: state.view });
      } else {
        abandonSmarts();
      }
    }
    // Always redraw, including on the path that has just asked the kernel: the mode or the
    // query has already changed what the grid shows and what its message says, and leaving the
    // previous state on screen until the answer arrives is a stale view.
    render();
  });
  modeButton.addEventListener("click", () => {
    state.mode = state.mode === PROP_MODE ? SMARTS_MODE : PROP_MODE;
    modeButton.textContent = state.mode === PROP_MODE ? "Properties" : "SMARTS";
    abandonSmarts();
    state.page = 0;
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

  observe("images", () => { state.images = { ...(model.get("images") || {}) }; render(); });
  // A new revision invalidates every depiction: the images this view holds are of the previous
  // render options. Dropping them puts spinners back, and the render that follows republishes
  // the visible window so the kernel knows what to send first.
  observe("revision", () => { state.images = {}; state.revision = model.get("revision"); render(); });
  observe("selection", () => { state.selection = new Set(model.get("selection") || []); render(); });
  // Render options change the image size and the page size, and Python republishes the whole
  // config when they do.
  observe("config", () => { config = model.get("config") || {}; applyConfig(); render(); });
  observe("smarts_result", () => {
    const result = model.get("smarts_result") || {};
    // Two guards, because the trait is shared by every view of the widget: the token says the
    // answer was meant for this grid, and the sequence says it answers the query still in its
    // box rather than one the user has replaced or abandoned.
    if (result.view !== state.view) return;
    if (result.seq !== state.smartsSeq) return;
    state.awaitingSmarts = false;
    state.smartsMatches = result.error ? new Set() : new Set(result.matches || []);
    state.message = result.error || "";
    state.page = 0; render();
  });
  observe("error", () => { state.message = model.get("error") || ""; render(); });

  /**
   * Detach from the model and remove the grid.
   *
   * The model outlives the view in anywidget, so a view that is dropped without this leaves a
   * permanent subscriber behind: re-running the cell would stack another set of handlers, and
   * each dead view would go on publishing `visible` from a detached grid, making the kernel
   * render images nobody can see.
   */
  function destroy() {
    if (destroyed) return;
    destroyed = true;
    for (const [event, handler] of observers) {
      // anywidget's model exposes Backbone's off. A host model without it keeps its handlers,
      // which is why every observer is guarded by `destroyed` as well.
      if (typeof model.off === "function") model.off(event, handler);
    }
    observers.length = 0;
    root.remove();
  }

  applyConfig();
  render();
  return { render, destroy, state, root };
}

export default {
  /**
   * anywidget entry point: mount one controller per view.
   *
   * The teardown is returned rather than dropped so that re-rendering a cell does not leave an
   * earlier controller subscribed to the same model.
   *
   * @param {{model: object, el: HTMLElement}} view
   * @returns {() => void} cleanup run when the view is destroyed
   */
  render({ model, el }) {
    const controller = createGrid(model, el);
    return () => controller.destroy();
  },
};

// Static document boot. cnotebook's to_html() writes the payload into the page before this
// module runs, so its presence is what distinguishes a saved document from a live widget.
if (typeof window !== "undefined" && window.__CNOTEBOOK_MOLGRID_STATIC__) {
  const data = window.__CNOTEBOOK_MOLGRID_STATIC__;
  const mountPoint = document.getElementById("molgrid-root") || document.body;
  createGrid(new StaticModel({ items: data.items, config: data.config, images: data.images, selection: data.selection || [], revision: 0 }), mountPoint);
}
