function render({ model, el }) {
    const gridId = model.get("grid_id");
    const globalName = "_MOLGRID_" + gridId;

    // Store model reference globally so iframe can access it
    window[globalName] = model;
    console.log("[MolGridWidget] Model stored as window." + globalName);

    // Add a class to the element
    el.classList.add("molgrid-anywidget");

    // Listen for postMessage from iframe
    window.addEventListener("message", (event) => {
        if (event.data && event.data.gridId === gridId && event.data.type === "MOLGRID_SELECTION") {
            const selectionJson = JSON.stringify(event.data.selection);
            model.set("selection", selectionJson);
            model.save_changes();
            console.log("[MolGridWidget] Selection synced to Python:", event.data.selection);
        }
    });
}

export default { render };
