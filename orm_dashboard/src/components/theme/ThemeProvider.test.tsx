// ThemeProvider: forcedTheme (Export Report chart stage) must never touch the saved preference, and must change nothing when absent.
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";
import { ThemeProvider, useTheme } from "./ThemeProvider";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

let host: HTMLDivElement;
let root: Root;
let toggle: () => void = () => {};
function Probe() {
  const { theme, toggleTheme } = useTheme();
  toggle = toggleTheme;
  return React.createElement("span", { id: "t" }, theme);
}
const shown = () => host.querySelector("#t")?.textContent;
async function mount(el: React.ReactElement) {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => { root.render(el); });
}

beforeEach(() => { window.localStorage.clear(); });
afterEach(async () => { await act(async () => { root.unmount(); }); host.remove(); });

describe("ThemeProvider default behaviour (no forcedTheme) is unchanged", () => {
  it("defaults to dark, restores the saved theme, saves it, and toggles", async () => {
    window.localStorage.setItem("xoop-dashboard-theme", "light");
    await mount(React.createElement(ThemeProvider, null, React.createElement(Probe)));
    expect(shown()).toBe("light");
    await act(async () => { toggle(); });
    expect(shown()).toBe("dark");
    expect(window.localStorage.getItem("xoop-dashboard-theme")).toBe("dark");
  });
  it("with nothing saved it shows dark", async () => {
    await mount(React.createElement(ThemeProvider, null, React.createElement(Probe)));
    expect(shown()).toBe("dark");
  });
});

describe("forcedTheme", () => {
  it("shows the forced theme even when the user saved the other one, and ignores toggling", async () => {
    window.localStorage.setItem("xoop-dashboard-theme", "dark");
    await mount(React.createElement(ThemeProvider, { forcedTheme: "light", children: React.createElement(Probe) }));
    expect(shown()).toBe("light");
    await act(async () => { toggle(); });
    expect(shown()).toBe("light");
  });
  it("never writes the user's saved preference", async () => {
    await mount(React.createElement(ThemeProvider, { forcedTheme: "light", children: React.createElement(Probe) }));
    expect(window.localStorage.getItem("xoop-dashboard-theme")).toBeNull();
  });
});
