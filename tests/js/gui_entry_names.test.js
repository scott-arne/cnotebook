import { beforeEach, describe, expect, it } from "vitest";
import { addObject, getState } from "../../vendor/3dmol-js-gui/src/state.js";

// C3D._resolved_entry_names mirrors this rule so it can refuse a conformer entry the
// GUI would rename out from under animate(). The Python mirror is tested against the
// same sequence in tests/test_c3d.py; asserting it here against the GUI's own addObject
// means a change to the rule fails a test on both sides rather than silently parting
// the two. The loader trims a name before calling addObject, so what arrives here is
// already trimmed.
const model = { getNumFrames: () => 1 };

beforeEach(() => {
  const state = getState();
  state.objects.clear();
  state.entryTree.length = 0;
});

describe("addObject naming", () => {
  it("gives each duplicate the first free _2, _3, ... suffix", () => {
    expect(addObject("lig", model, 0)).toBe("lig");
    expect(addObject("lig", model, 1)).toBe("lig_2");
    expect(addObject("lig", model, 2)).toBe("lig_3");
  });

  it("builds the suffix from the requested name, not from the resolved one", () => {
    addObject("lig", model, 0);
    addObject("lig", model, 1);
    expect(addObject("lig_2", model, 2)).toBe("lig_2_2");
  });

  it("registers the assigned name, so nothing else may take it", () => {
    addObject("lig", model, 0);
    addObject("lig", model, 1);
    expect([...getState().objects.keys()]).toEqual(["lig", "lig_2"]);
  });
});
