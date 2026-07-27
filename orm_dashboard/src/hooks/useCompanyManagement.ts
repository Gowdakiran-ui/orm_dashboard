import { useState } from "react";
import { onboardClient, deleteClient } from "@/lib/api";

export function useCompanyManagement(
  clientId: string | null,
  clients: any[],
  setClientsRefreshKey: (fn: (k: number) => number) => void,
  handleSelectCompany: (id: string | null) => void,
  abortCurrentFetches: () => void
) {
  const [addOpen, setAddOpen] = useState(false);
  const [addName, setAddName] = useState("");
  const [addIndustry, setAddIndustry] = useState("");
  const [addLoading, setAddLoading] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<any | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  async function handleAddCompany() {
    if (!addName.trim()) {
      setAddError("Company name is required");
      return;
    }
    setAddLoading(true);
    setAddError(null);
    try {
      const created = await onboardClient({
        name: addName.trim(),
        industry: addIndustry.trim() || undefined,
        primary_entity_name: addName.trim(),
      });
      setAddOpen(false);
      setAddName("");
      setAddIndustry("");
      setClientsRefreshKey(k => k + 1);
      handleSelectCompany(created.id);
    } catch (e: any) {
      setAddError(e.message || "Failed to add company");
    } finally {
      setAddLoading(false);
    }
  }

  async function handleDeleteCompany() {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    try {
      if (deleteTarget.id === clientId) {
        abortCurrentFetches();
      }
      await deleteClient(deleteTarget.id);
      
      if (deleteTarget.id === clientId) {
        const remainingClients = clients.filter((c: any) => c.id !== deleteTarget.id);
        if (remainingClients.length > 0) {
          handleSelectCompany(remainingClients[0].id);
        } else {
          handleSelectCompany(null);
        }
      }
      
      setDeleteTarget(null);
      setClientsRefreshKey(k => k + 1);
    } catch (e: any) {
      console.error("Failed to delete company", e);
    } finally {
      setDeleteLoading(false);
    }
  }

  return {
    addOpen,
    setAddOpen,
    addName,
    setAddName,
    addIndustry,
    setAddIndustry,
    addLoading,
    addError,
    setAddError,
    deleteTarget,
    setDeleteTarget,
    deleteLoading,
    handleDeleteCompany,
    handleAddCompany
  };
}

