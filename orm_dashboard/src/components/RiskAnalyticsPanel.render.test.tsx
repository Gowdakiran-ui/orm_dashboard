// Renders the real Risk & Alert Profile panel (jsdom): the alert timeline shows an empty state, not invented days, when there are no open alerts.
import { describe, it, expect, vi, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));

import { RiskAnalyticsPanel } from "./RiskAnalyticsPanel";
import { ThemeProvider } from "@/components/theme/ThemeProvider";

let host: HTMLDivElement;
let root: Root;

async function mount(props: any) {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root.render(React.createElement(ThemeProvider, null, React.createElement(RiskAnalyticsPanel, props)));
  });
}
afterEach(async () => { await act(async () => { root.unmount(); }); host.remove(); });

const timelineCard = () => {
  const title = Array.from(host.querySelectorAll("*")).find(
    el => el.children.length < 3 && /^Daily Alerts Trigger Volume Timeline/i.test(el.textContent?.trim() || "")
  );
  return title!.closest("[class*='rounded-3xl']") as HTMLElement;
};

describe("Daily Alerts timeline", () => {
  it("with no open alerts shows the empty state and no chart, so no padded zero days, peak or average", async () => {
    await mount({ alertTimelineData: [] });
    const card = timelineCard();
    expect(card.textContent).toContain("No open alerts");
    expect(card.textContent).toContain("Nothing unacknowledged for this client");
    expect(card.querySelector(".recharts-responsive-container")).toBeNull();
    expect(card.textContent).not.toMatch(/Peak:|Avg \(/);
  });
  it("with alerts renders the chart over the real alert days only (no empty-state text)", async () => {
    await mount({ alertTimelineData: [{ date: "Oct 8", count: 1 }] });
    const card = timelineCard();
    expect(card.querySelector(".recharts-responsive-container")).not.toBeNull();
    expect(card.textContent).not.toContain("Nothing unacknowledged for this client");
  });
});
