// Renders the real sidebar (jsdom): the Delete Company control is shown to super admins only. The server refuses a client user's DELETE
// with 403 anyway; hiding the button keeps them from clicking a control that cannot work.
import { describe, it, expect, vi, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot, Root } from "react-dom/client";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }) }));
vi.mock("@/lib/api", () => ({ logout: vi.fn() }));

import { Sidebar } from "./Sidebar";
import { ThemeProvider } from "@/components/theme/ThemeProvider";

let host: HTMLDivElement;
let root: Root;

async function mount(isSuperAdmin: boolean | undefined, onDelete = vi.fn()) {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  const clients = [{ id: "c1", name: "Godrej Properties" }];
  const props: any = {
    clientId: "c1", activeTab: "overview", filteredClients: clients, companySearch: "", threatLevel: "LOW", pipelineRunning: false,
    pipelineStatus: null, lastUpdatedAt: null, clients, onSelectCompany: vi.fn(), onSearchChange: vi.fn(), onAddCompanyClick: vi.fn(),
    onDeleteCompanyClick: onDelete, onRunPipeline: vi.fn(), onSelectTab: vi.fn(), isSuperAdmin,
  };
  await act(async () => { root.render(React.createElement(ThemeProvider, null, React.createElement(Sidebar, props))); });
  return onDelete;
}
afterEach(async () => { await act(async () => { root.unmount(); }); host.remove(); });

describe("Sidebar: Delete Company", () => {
  it("is shown to a super admin and calls the handler with the selected company", async () => {
    const onDelete = await mount(true);
    const btn = host.querySelector("[data-testid='delete-company']") as HTMLButtonElement;
    expect(btn).not.toBeNull();
    await act(async () => { btn.click(); });
    expect(onDelete).toHaveBeenCalledWith({ id: "c1", name: "Godrej Properties" });
  });

  it("is not shown to a client user, or when the role is not known yet", async () => {
    await mount(false);
    expect(host.querySelector("[data-testid='delete-company']")).toBeNull();
    expect(host.textContent).not.toContain("Delete");
    await act(async () => { root.unmount(); });
    host.remove();
    await mount(undefined);
    expect(host.querySelector("[data-testid='delete-company']")).toBeNull();
  });

  it("still shows Add and Run Pipeline to a client user", async () => {
    await mount(false);
    expect(host.querySelector("[title='Add Company']")).not.toBeNull();
    expect(host.querySelector("[title='Run Pipeline']")).not.toBeNull();
  });
});
